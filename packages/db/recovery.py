"""Consistent pg_dump -> age -> off-host backup; guarded isolated restoration.

Database credentials are read from environment variables, never command arguments.
Clear database dumps are streamed through pipes and are never stored on disk.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ipaddress
import stat
import subprocess
import tempfile
from uuid import uuid4


class RecoveryError(RuntimeError):
    pass


def tool_environment():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('OPENAI_', 'PG')) and not k.endswith('DATABASE_URL')
            and not str(v).startswith(('postgresql://', 'postgres://'))}


def protect_windows_directory(path):
    if os.name != 'nt':
        return
    quoted = str(path).replace("'", "''")
    script = """$ErrorActionPreference='Stop'; $p='%s';
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User;
$a=Get-Acl -LiteralPath $p;$a.SetAccessRuleProtection($true,$false);
foreach($existing in @($a.Access)){$a.RemoveAccessRuleAll($existing)};
foreach($s in @($u.Value,'S-1-5-18','S-1-5-32-544')){
$id=New-Object Security.Principal.SecurityIdentifier($s);
$r=New-Object Security.AccessControl.FileSystemAccessRule($id,'FullControl','ContainerInherit,ObjectInherit','None','Allow');
$a.AddAccessRule($r)};([IO.DirectoryInfo]::new($p)).SetAccessControl($a)
""" % quoted
    run_checked(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], timeout=30)


def require_private_identity(path):
    if os.name != 'nt':
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RecoveryError('Restore identity must allow owner access only')
        return
    quoted = str(path).replace("'", "''")
    script = """$ErrorActionPreference='Stop';$p='%s';
$u=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
$allowed=@($u,'S-1-5-18','S-1-5-32-544');$a=Get-Acl -LiteralPath $p;
foreach($r in $a.Access){if($r.AccessControlType -eq 'Allow'){
$s=$r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;
if($s -notin $allowed){throw 'Restore identity permissions are too broad'}}}
""" % quoted
    run_checked(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], timeout=30)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def digest_file(path):
    checksum = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def private_directory(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect_windows_directory(path)
    if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RecoveryError('Recovery state directory must allow owner access only')
    return path


def connection_environment(dsn, *, readonly=False):
    from psycopg.conninfo import conninfo_to_dict
    try:
        info = conninfo_to_dict(dsn)
    except Exception:
        raise RecoveryError('Invalid database connection settings; details withheld') from None
    if not info.get('dbname'):
        raise RecoveryError('Database name is required')
    # Ambient libpq settings must not change the destination selected by the DSN.
    env = tool_environment()
    mapping = {'host': 'PGHOST', 'hostaddr': 'PGHOSTADDR', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
               'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE',
               'sslrootcert': 'PGSSLROOTCERT', 'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY',
               'connect_timeout': 'PGCONNECT_TIMEOUT', 'options': 'PGOPTIONS'}
    for key, value in info.items():
        if key not in mapping:
            raise RecoveryError('Unsupported database option; use an explicit direct connection')
        env[mapping[key]] = str(value)
    env.setdefault('PGCONNECT_TIMEOUT', '10')
    if readonly:
        env['PGOPTIONS'] = env.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on'
    return env, info['dbname']


@contextmanager
def private_libpq_environment(dsn, *, readonly=False):
    env, database = connection_environment(dsn, readonly=readonly)
    password = env.pop('PGPASSWORD', None)
    if password is None:
        yield env, database
        return
    with tempfile.TemporaryDirectory(prefix='industrial-ai-libpq-') as folder:
        protect_windows_directory(folder)
        path = Path(folder)/'pgpass'
        def escape(value):
            return str(value).replace('\\', '\\\\').replace(':', '\\:')
        fields = (env.get('PGHOST', '*'), env.get('PGPORT', '5432'), database,
                  env.get('PGUSER', '*'), password)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(':'.join(escape(v) for v in fields)+'\n')
        env['PGPASSFILE'] = str(path)
        yield env, database


def require_tool(name):
    path = shutil.which(name)
    if not path:
        raise RecoveryError(name + ' is required on PATH')
    return path


def run_checked(arguments, *, env=None, input_data=None, timeout=600):
    try:
        result = subprocess.run(arguments, input=input_data, capture_output=True,
                                env=env if env is not None else tool_environment(),
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RecoveryError(Path(arguments[0]).name + ' could not complete') from None
    if result.returncode:
        # Tool stderr can contain source material or libpq connection details.
        raise RecoveryError(Path(arguments[0]).name + ' failed; inspect restricted service logs')
    return result.stdout


def fingerprint(db):
    from psycopg import sql
    db.execute("SET TIME ZONE 'UTC'")
    tables = {}
    for (name,) in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall():
        rows = db.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} t').format(sql.Identifier('public', name))).fetchall()
        values = sorted(canonical(json.loads(row[0])) for row in rows)
        tables[name] = {'rows': len(values), 'sha256': sha256(b'\n'.join(values)).hexdigest()}
    issues, revisions = [], []
    if 'issues' in tables:
        for issue_date, content in db.execute("SELECT issue_date,content FROM issues WHERE state='published' AND validated ORDER BY issue_date,id"):
            if content.get('synthetic') is not False:
                continue
            bilingual = all(all(isinstance(story.get(field), dict) and story[field].get(locale)
                                for field in ('title', 'summary', 'why', 'limitation') for locale in ('en', 'zh'))
                            for story in content.get('stories', []))
            issues.append({'date': issue_date, 'contentSha256': sha256(canonical(content)).hexdigest(),
                           'bilingual': bool(content.get('stories')) and bilingual})
    if 'edition_revisions' in tables:
        for identifier, revision, content, review in db.execute('SELECT issue_id,revision,content,review FROM edition_revisions ORDER BY issue_id,revision'):
            revisions.append({'issueId': identifier, 'revision': revision,
                              'contentSha256': sha256(canonical(content)).hexdigest(),
                              'reviewSha256': sha256(canonical(review)).hexdigest()})
    real = db.execute("SELECT count(*) FROM raw_articles WHERE coalesce((raw_metadata->>'synthetic')::boolean,false)=false").fetchone()[0] if 'raw_articles' in tables else 0
    return {'tables': tables, 'realArticles': real, 'publishedIssues': issues, 'revisions': revisions}


@contextmanager
def source_snapshot(dsn):
    import psycopg
    try:
        with psycopg.connect(dsn, connect_timeout=10) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            snapshot = db.execute('SELECT pg_export_snapshot()').fetchone()[0]
            yield db, snapshot
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError('Read-only source snapshot failed') from None


def pipe_commands(first, second, *, first_env=None, second_env=None):
    """Connect tools without a cleartext temporary file; never echo tool stderr."""
    a = b = None
    with tempfile.TemporaryFile() as first_errors, tempfile.TemporaryFile() as second_errors:
        try:
            a = subprocess.Popen(first, stdout=subprocess.PIPE, stderr=first_errors,
                                 env=first_env if first_env is not None else tool_environment())
            b = subprocess.Popen(second, stdin=a.stdout, stdout=subprocess.DEVNULL,
                                 stderr=second_errors,
                                 env=second_env if second_env is not None else tool_environment())
            a.stdout.close()
            b.wait(timeout=900)
            a.wait(timeout=30)
            if a.returncode or b.returncode:
                raise RecoveryError('Encrypted backup/restore stream failed; no cleartext dump retained')
        except (OSError, subprocess.TimeoutExpired):
            raise RecoveryError('Encrypted backup/restore stream could not complete') from None
        finally:
            for process in (a, b):
                if process is not None and process.poll() is None:
                    process.kill(); process.wait()


def destination_path(destination, *, allow_test_transport=False):
    if destination.startswith('test-local:'):
        if not allow_test_transport:
            raise RecoveryError('Local transport is test-only; production requires rclone off-host storage')
        return 'test-local', private_directory(destination.removeprefix('test-local:'))
    if not destination.startswith('rclone:'):
        raise RecoveryError('Production destination must use rclone:REMOTE:PATH')
    remote = destination.removeprefix('rclone:').rstrip('/')
    if re.fullmatch(r'[A-Za-z0-9_-]+:[A-Za-z0-9_./-]+', remote) is None or '..' in remote.split('/'):
        raise RecoveryError('Invalid off-host destination; credentials belong in protected rclone config')
    rclone = require_tool('rclone')
    if os.getenv('BACKUP_OFFHOST_APPROVED') != 'true':
        raise RecoveryError('Off-host storage must be independently approved before uploading')
    if any(key.startswith('RCLONE_') and key not in {'RCLONE_CONFIG', 'RCLONE_CONFIG_PASS'}
           for key in os.environ):
        raise RecoveryError('Rclone environment overrides are not allowed for verified backups')
    if any(key in os.environ for key in ('AWS_ENDPOINT_URL', 'AWS_ENDPOINT_URL_S3',
                                         'STORAGE_EMULATOR_HOST', 'AZURE_STORAGE_CONNECTION_STRING')):
        raise RecoveryError('Ambient cloud endpoint/emulator overrides are not allowed')
    config_file = Path(os.getenv('RCLONE_CONFIG', '')).resolve()
    if not os.getenv('RCLONE_CONFIG') or not config_file.is_file():
        raise RecoveryError('An explicit private RCLONE_CONFIG file is required')
    require_private_identity(config_file)
    try:
        configs = json.loads(run_checked([rclone, 'config', 'dump']))
        config = configs[remote.split(':', 1)[0]]
        backend = config['type']
    except (ValueError, KeyError, TypeError):
        raise RecoveryError('Off-host remote configuration could not be validated') from None
    if backend not in {'s3', 'b2', 'azureblob', 'googlecloudstorage'}:
        raise RecoveryError('Local, alias or unreviewed rclone backend is not permitted')
    if any(str(config.get(key, '')).lower() in {'1', 'true', 'yes'}
           for key in ('insecure_skip_verify', 'no_check_certificate', 'disable_tls', 'use_emulator')):
        raise RecoveryError('Off-host transport cannot disable certificate or TLS verification')
    endpoint = config.get('endpoint')
    if backend == 's3' and not endpoint and config.get('provider') != 'AWS':
        raise RecoveryError('Non-AWS S3-compatible storage requires an explicit HTTPS endpoint')
    if endpoint:
        from urllib.parse import urlsplit
        parsed = urlsplit(endpoint)
        if parsed.scheme != 'https' or parsed.username or parsed.password:
            raise RecoveryError('Custom off-host endpoints require HTTPS without inline credentials')
        host = parsed.hostname
    else:
        host = None  # Official cloud-provider default endpoint, still subject to operator attestation.
    if host is not None:
        try:
            addresses = {record[4][0] for record in socket.getaddrinfo(host, None)}
        except (OSError, TypeError):
            raise RecoveryError('Off-host endpoint resolution failed') from None
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise RecoveryError('Off-host endpoint cannot resolve to a local/private address')
    return 'rclone', remote


def publish_file(path, destination, *, allow_test_transport=False):
    kind, target = destination_path(destination, allow_test_transport=allow_test_transport)
    name = Path(path).name
    if kind == 'test-local':
        final, temporary = target/name, target/(name + '.uploading')
        if final.exists():
            raise RecoveryError('Backup object already exists')
        shutil.copyfile(path, temporary)
        if digest_file(path) != digest_file(temporary):
            temporary.unlink(missing_ok=True)
            raise RecoveryError('Off-host copy checksum mismatch')
        temporary.replace(final)
        return str(final)
    final, temporary = target+'/'+name, target+'/'+name+'.uploading'
    run_checked([require_tool('rclone'), 'copyto', str(path), temporary])
    # Compare downloaded ciphertext before publishing its final name.
    checksum = sha256(run_checked([require_tool('rclone'), 'cat', temporary])).hexdigest()
    if checksum != digest_file(path):
        raise RecoveryError('Off-host ciphertext checksum mismatch')
    run_checked([require_tool('rclone'), 'moveto', temporary, final])
    return 'rclone:' + final


def retention_candidates(names):
    """Retain newest backup for seven dates and four ISO weeks; ignore foreign files."""
    items = []
    for name in names:
        match = re.fullmatch(r'(industrial-ai-(\d{8}T\d{6}Z)-[0-9a-f]{12})\.manifest\.json\.age', name)
        if match:
            items.append((datetime.strptime(match[2], '%Y%m%dT%H%M%SZ'), match[1]))
    dates, weeks, keep = set(), set(), set()
    for timestamp, stem in sorted(items, reverse=True):
        date_key, week_key = timestamp.date(), timestamp.isocalendar()[:2]
        if date_key not in dates and len(dates) < 7:
            dates.add(date_key); keep.add(stem)
        if week_key not in weeks and len(weeks) < 4:
            weeks.add(week_key); keep.add(stem)
    return sorted(stem for _, stem in items if stem not in keep)


def prune(destination, *, apply=False, allow_test_transport=False):
    kind, target = destination_path(destination, allow_test_transport=allow_test_transport)
    if kind == 'test-local':
        names = [path.name for path in target.iterdir() if path.is_file()]
    else:
        names = run_checked([require_tool('rclone'), 'lsf', '--files-only', target]).decode().splitlines()
    candidates = retention_candidates(names)
    if apply:
        for stem in candidates:
            for suffix in ('.manifest.json.age', '.dump.age'):
                name = stem + suffix
                if kind == 'test-local':
                    (target/name).unlink(missing_ok=True)
                else:
                    run_checked([require_tool('rclone'), 'deletefile', target+'/'+name])
    return {'apply': apply, 'expiredBackupIds': candidates, 'policy': 'seven daily dates and four ISO weeks'}


def backup(dsn, recipient, destination, *, state_dir='/var/lib/industrial-ai/backups',
           state_file=None, allow_test_transport=False):
    if not isinstance(recipient, str) or re.fullmatch(r'age1[0-9a-z]{20,200}', recipient) is None:
        raise RecoveryError('An age X25519 public recipient is required; no password encryption')
    dump, age = require_tool('pg_dump'), require_tool('age')
    destination_path(destination, allow_test_transport=allow_test_transport)
    _, database = connection_environment(dsn, readonly=True)
    state = private_directory(state_dir)
    identifier = 'industrial-ai-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:12]
    archive = state/(identifier + '.dump.age')
    partial = state/(identifier + '.dump.age.partial')
    encrypted_manifest = state/(identifier + '.manifest.json.age')
    supplemental = None
    if state_file is not None:
        value = Path(state_file).read_bytes()
        if len(value) > 1024 * 1024:
            raise RecoveryError('Supplemental budget state exceeds the bounded backup size')
        try:
            parsed = json.loads(value)
        except ValueError:
            raise RecoveryError('Supplemental state must be the existing budget JSON ledger') from None
        if not isinstance(parsed, dict) or not isinstance(parsed.get('requests'), list) or 'limit' not in parsed:
            raise RecoveryError('Supplemental state must be the existing budget JSON ledger')
        supplemental = {'name': 'budget.json', 'sha256': sha256(value).hexdigest(),
                        'dataBase64': base64.b64encode(value).decode('ascii')}
    try:
        with source_snapshot(dsn) as (db, snapshot), private_libpq_environment(dsn, readonly=True) as (env, _):
            before = fingerprint(db)
            database = db.execute('SELECT current_database()').fetchone()[0]
            pipe_commands([dump, '--format=custom', '--no-owner', '--no-acl', '--no-password', '--snapshot='+snapshot],
                          [age, '--encrypt', '--recipient', recipient, '--output', str(partial)], first_env=env)
        partial.replace(archive)
        manifest = {'format': 'industrial-ai-backup-v1', 'backupId': identifier,
                    'createdAt': datetime.now(timezone.utc).isoformat(), 'sourceDatabase': database,
                    'archiveName': archive.name, 'archiveSha256': digest_file(archive), 'fingerprint': before}
        if supplemental is not None:
            manifest['supplementalState'] = supplemental
        run_checked([age, '--encrypt', '--recipient', recipient, '--output', str(encrypted_manifest)],
                    input_data=canonical(manifest))
        # Manifest is the commit marker and is encrypted/authenticated too.
        remote_archive = publish_file(archive, destination, allow_test_transport=allow_test_transport)
        remote_manifest = publish_file(encrypted_manifest, destination, allow_test_transport=allow_test_transport)
        return {'backupId': identifier, 'archive': str(archive), 'manifest': str(encrypted_manifest),
                'remoteArchive': remote_archive, 'remoteManifest': remote_manifest,
                'realArticles': before['realArticles'], 'publishedDates': [i['date'] for i in before['publishedIssues']],
                'revisionCount': len(before['revisions']), 'encrypted': True,
                'budgetStateIncluded': supplemental is not None}
    finally:
        partial.unlink(missing_ok=True)


def restore(archive, identity_file, target_dsn, expected_manifest, *, state_output=None):
    import psycopg
    archive, identity_file, expected_manifest = map(lambda p: Path(p).resolve(), (archive, identity_file, expected_manifest))
    if not all(path.is_file() for path in (archive, identity_file, expected_manifest)):
        raise RecoveryError('Archive, protected identity and encrypted manifest files are required')
    require_private_identity(identity_file)
    env, target_name = connection_environment(target_dsn)
    if re.fullmatch(r'industrial_ai_restore_[a-z0-9_]{1,40}', target_name) is None:
        raise RecoveryError('Restore target must be an explicitly isolated industrial_ai_restore_* database')
    age, pg_restore = require_tool('age'), require_tool('pg_restore')
    try:
        manifest = json.loads(run_checked([age, '--decrypt', '--identity', str(identity_file), str(expected_manifest)]))
    except (ValueError, UnicodeError):
        raise RecoveryError('Encrypted manifest is invalid') from None
    if manifest.get('format') != 'industrial-ai-backup-v1' or manifest.get('sourceDatabase') == target_name:
        raise RecoveryError('Restore manifest/source-target isolation check failed')
    if manifest.get('archiveName') != archive.name or manifest.get('archiveSha256') != digest_file(archive):
        raise RecoveryError('Encrypted archive does not match its integrity-checked manifest')
    restored_state = None
    if state_output is not None:
        output = Path(state_output).resolve()
        if output.name != 'budget.json' or output.parent.name != target_name or output.exists():
            raise RecoveryError('Supplemental state can only be restored to a new isolated-target budget.json path')
        try:
            supplemental = manifest['supplementalState']
            restored_state = base64.b64decode(supplemental['dataBase64'], validate=True)
            if len(restored_state) > 1024*1024 or sha256(restored_state).hexdigest() != supplemental['sha256']:
                raise ValueError('state checksum')
        except (KeyError, ValueError, TypeError):
            raise RecoveryError('Supplemental budget state is absent or failed integrity validation') from None
    try:
        with psycopg.connect(target_dsn, autocommit=True, connect_timeout=10) as db:
            actual_name = db.execute('SELECT current_database()').fetchone()[0]
            if actual_name != target_name or actual_name == manifest['sourceDatabase']:
                raise RecoveryError('Resolved restore destination does not match an isolated target')
            # A second restorer must not race the emptiness check; pg_restore cannot overwrite this DB.
            if not db.execute("SELECT pg_try_advisory_lock(hashtext('industrial-ai-isolated-restore'))").fetchone()[0]:
                raise RecoveryError('Another restore owns the target database lock')
            occupied = db.execute('''SELECT
                EXISTS(SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_%') OR
                EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public') OR
                EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public') OR
                EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public') OR
                EXISTS(SELECT 1 FROM pg_extension WHERE extname<>'plpgsql') OR
                EXISTS(SELECT 1 FROM pg_event_trigger) OR EXISTS(SELECT 1 FROM pg_largeobject_metadata)''').fetchone()[0]
            if occupied:
                raise RecoveryError('Restore target is not empty; refusing to overwrite it')
            with private_libpq_environment(target_dsn) as (restore_env, _):
                pipe_commands([age, '--decrypt', '--identity', str(identity_file), str(archive)],
                              [pg_restore, '--dbname='+target_name, '--single-transaction', '--exit-on-error', '--no-owner', '--no-acl', '--no-password'], second_env=restore_env)
            db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            restored = fingerprint(db)
            db.execute('ROLLBACK')
            if restored != manifest['fingerprint']:
                raise RecoveryError('Restored database fingerprint does not match the source snapshot')
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError('Isolated restoration failed; original source was never changed') from None
    if restored_state is not None:
        private_directory(output.parent)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(restored_state)
    return {'restored': True, 'targetDatabase': target_name, 'realArticles': restored['realArticles'],
            'publishedDates': [i['date'] for i in restored['publishedIssues']],
            'bilingualComplete': all(i['bilingual'] for i in restored['publishedIssues']),
            'revisionCount': len(restored['revisions']), 'tableCount': len(restored['tables']),
            'budgetStateRestored': restored_state is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('backup')
    make.add_argument('--database-env', default='DATABASE_URL')
    make.add_argument('--recipient-env', default='BACKUP_AGE_RECIPIENT')
    make.add_argument('--destination', required=True)
    make.add_argument('--state-dir', default='/var/lib/industrial-ai/backups')
    make.add_argument('--state-file', help='Optional existing November budget.json ledger, encrypted in the manifest')
    recover = sub.add_parser('restore')
    recover.add_argument('--archive', required=True)
    recover.add_argument('--identity-file', required=True)
    recover.add_argument('--target-env', default='RESTORE_DATABASE_URL')
    recover.add_argument('--expected-manifest', required=True)
    recover.add_argument('--state-output', help='New budget.json under a directory named after the isolated target database')
    expire = sub.add_parser('prune')
    expire.add_argument('--destination', required=True)
    expire.add_argument('--apply', action='store_true', help='Without this flag only a retention plan is returned')
    args = parser.parse_args(argv)
    try:
        if args.command == 'backup':
            result = backup(os.environ[args.database_env], os.environ[args.recipient_env], args.destination,
                            state_dir=args.state_dir, state_file=args.state_file)
        elif args.command == 'restore':
            result = restore(args.archive, args.identity_file, os.environ[args.target_env], args.expected_manifest,
                             state_output=args.state_output)
        else:
            result = prune(args.destination, apply=args.apply)
        print(json.dumps(result))
        return 0
    except (KeyError, RecoveryError):
        print(json.dumps({'status': 'failed', 'error': 'RecoveryError',
                          'message': 'Backup/restore rejected or failed; credentials and tool output withheld'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
