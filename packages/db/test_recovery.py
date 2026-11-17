"""Backup security gates and opt-in encrypted PostgreSQL recovery roundtrip."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from packages.db import recovery


class RecoverySafetyTests(unittest.TestCase):
    @contextmanager
    def remote_config(self, value):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'rclone.conf';path.write_text('test-placeholder-only');path.chmod(0o600)
            with patch.dict(os.environ, {'BACKUP_OFFHOST_APPROVED': 'true', 'RCLONE_CONFIG': str(path)}), \
                 patch.object(recovery, 'require_tool', return_value='rclone'), \
                 patch.object(recovery, 'run_checked', return_value=json.dumps({'remote': value}).encode()):
                yield

    def test_libpq_password_uses_private_temp_file_not_child_environment(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'never-forward-this-value',
                                     'DATABASE_URL': 'never-forward-this-dsn'}):
            with recovery.private_libpq_environment('postgresql://reader:test_password@localhost:5432/source', readonly=True) as (env, name):
                self.assertEqual(name, 'source')
                self.assertNotIn('PGPASSWORD', env)
                self.assertNotIn('OPENAI_API_KEY', env)
                self.assertNotIn('DATABASE_URL', env)
                password_file = Path(env['PGPASSFILE'])
                self.assertTrue(password_file.is_file())
                self.assertEqual(password_file.read_text(), 'localhost:5432:source:reader:test_password\n')
                self.assertIn('default_transaction_read_only=on', env['PGOPTIONS'])
            self.assertFalse(password_file.exists())

    def test_malformed_connection_settings_never_escape_redacted_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder)/name for name in ('dump.age', 'identity.txt', 'manifest.age')]
            for path in paths:
                path.write_bytes(b'placeholder'); path.chmod(0o600)
            with patch.dict(os.environ, {'UNIT_DATABASE_URL': 'host=localhost password=secret-value invalid-token'}), \
                 patch.object(recovery, 'require_private_identity'), patch('builtins.print') as output:
                result = recovery.main(['restore', '--target-env', 'UNIT_DATABASE_URL',
                    '--archive', str(paths[0]), '--identity-file', str(paths[1]), '--expected-manifest', str(paths[2])])
            self.assertEqual(result, 1)
            self.assertNotIn('secret-value', repr(output.call_args_list))
        with self.assertRaisesRegex(recovery.RecoveryError, 'details withheld'):
            recovery.connection_environment('host=localhost password=secret-value invalid-token')

    def test_unknown_database_options_fail_closed(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.connection_environment('postgresql://localhost/source?application_name=unexpected')

    def test_local_transport_cannot_be_used_accidentally_in_production(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.destination_path('test-local:/tmp/not-offhost')
        for remote in ('file:///tmp', 'rclone:remote:../../escape', 'rclone:https://user:password@host', 'rclone:--flag:path'):
            with self.subTest(remote=remote), self.assertRaises(recovery.RecoveryError):
                recovery.destination_path(remote)

    def test_copy_checksum_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'backup.dump.age'
            source.write_bytes(b'ciphertext-placeholder-only')
            target = Path(folder)/'offhost'; target.mkdir(mode=0o700)
            copied = recovery.publish_file(source, 'test-local:'+str(target), allow_test_transport=True)
            self.assertEqual(recovery.digest_file(source), recovery.digest_file(copied))
            with self.assertRaises(recovery.RecoveryError):
                recovery.publish_file(source, 'test-local:'+str(target), allow_test_transport=True)
            self.assertFalse((target/(source.name+'.uploading')).exists())

    def test_recipient_only_encryption_is_required(self):
        for recipient in ('', 'password', 'AGE-SECRET-KEY-not-a-recipient', '-r dangerous'):
            with self.subTest(recipient=recipient), self.assertRaises(recovery.RecoveryError):
                recovery.backup('postgresql://localhost/source', recipient, 'rclone:remote:archive')

    def test_rclone_local_backend_is_not_offhost(self):
        with self.remote_config({'type': 'local'}):
            with self.assertRaisesRegex(recovery.RecoveryError, 'unreviewed rclone backend'):
                recovery.destination_path('rclone:remote:archive')

    def test_sftp_without_pinned_host_keys_is_not_a_supported_backend(self):
        with self.remote_config({'type': 'sftp', 'host': 'backup.invalid'}):
            with self.assertRaisesRegex(recovery.RecoveryError, 'unreviewed rclone backend'):
                recovery.destination_path('rclone:remote:archive')

    def test_insecure_env_and_private_endpoint_are_rejected(self):
        with self.remote_config({'type': 's3', 'provider': 'AWS'}):
            with patch.dict(os.environ, {'RCLONE_INSECURE_SKIP_VERIFY': 'true'}):
                with self.assertRaisesRegex(recovery.RecoveryError, 'environment overrides'):
                    recovery.destination_path('rclone:remote:archive')
        with self.remote_config({'type': 's3', 'provider': 'Other', 'endpoint': 'https://127.0.0.1'}):
            with self.assertRaisesRegex(recovery.RecoveryError, 'local/private'):
                recovery.destination_path('rclone:remote:archive')

    def test_approved_cloud_config_uses_protected_file_without_transport_overrides(self):
        with self.remote_config({'type': 's3', 'provider': 'AWS'}):
            self.assertEqual(recovery.destination_path('rclone:remote:archive'), ('rclone', 'remote:archive'))

    def test_sftp_and_insecure_overrides_are_not_supported(self):
        with patch.dict(os.environ, {'BACKUP_OFFHOST_APPROVED': 'true',
                                     'RCLONE_INSECURE_SKIP_VERIFY': 'true'}), \
             patch.object(recovery, 'require_tool', return_value='rclone'):
            with self.assertRaises(recovery.RecoveryError):
                recovery.destination_path('rclone:remote:archive')
        with patch.dict(os.environ, {'BACKUP_OFFHOST_APPROVED': 'true'}), \
             patch.object(recovery, 'require_tool', return_value='rclone'), \
             patch.object(recovery, 'run_checked', return_value=b'{"remote":{"type":"sftp","host":"backup.example.org"}}'):
            with self.assertRaises(recovery.RecoveryError):
                recovery.destination_path('rclone:remote:archive')

    def test_retention_is_dry_run_until_explicit_and_ignores_unrecognized_files(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for number in range(40):
                day = datetime(2026, 11, 16, tzinfo=timezone.utc)-timedelta(days=number)
                stem = 'industrial-ai-'+day.strftime('%Y%m%dT%H%M%SZ')+'-'+f'{number:012x}'
                for suffix in ('.manifest.json.age', '.dump.age'):
                    (root/(stem+suffix)).write_bytes(b'ciphertext-only')
            foreign = root/'unrelated-file';foreign.write_text('preserve')
            plan = recovery.prune('test-local:'+folder, allow_test_transport=True)
            self.assertTrue(plan['expiredBackupIds'])
            self.assertEqual(len(list(root.iterdir())), 81)
            recovery.prune('test-local:'+folder, apply=True, allow_test_transport=True)
            self.assertTrue(foreign.exists())
            self.assertLessEqual(len(list(root.glob('*.manifest.json.age'))), 11)

    def test_restore_nonisolated_target_fails_before_any_tool_or_database(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder)/name for name in ('dump.age', 'identity.txt', 'manifest.age')]
            for path in paths:
                path.write_bytes(b'not-a-real-key-or-archive'); path.chmod(0o600)
            with patch.object(recovery, 'require_tool', side_effect=AssertionError('No tool should run')):
                for target in ('digest', 'production', 'postgres', 'industrial_ai_restore_'):
                    with self.subTest(target=target), self.assertRaises(recovery.RecoveryError):
                        recovery.restore(paths[0], paths[1], 'postgresql://localhost/'+target, paths[2])

    def test_cli_failure_does_not_echo_dsn_or_secret(self):
        with patch.dict(os.environ, {'UNIT_DATABASE_URL': 'postgresql://user:secret-value@localhost/db'}), \
             patch.object(recovery, 'backup', side_effect=recovery.RecoveryError('secret-value')), \
             patch('builtins.print') as output:
            result = recovery.main(['backup', '--database-env', 'UNIT_DATABASE_URL',
                '--recipient-env', 'MISSING_RECIPIENT_FOR_TEST', '--destination', 'rclone:remote:archive'])
        self.assertEqual(result, 1)
        self.assertNotIn('secret-value', repr(output.call_args_list))


@unittest.skipUnless(os.getenv('RUN_RECOVERY_INTEGRATION') == '1',
                     'Explicit isolated PostgreSQL/age recovery integration required')
class RecoveryPostgresTests(unittest.TestCase):
    def test_encrypted_offhost_roundtrip_rejects_reuse_and_preserves_hashes(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        admin_url = os.getenv('TEST_RECOVERY_ADMIN_URL') or os.getenv('TEST_DATABASE_URL')
        self.assertTrue(admin_url, 'Dedicated TEST_RECOVERY_ADMIN_URL/TEST_DATABASE_URL required')
        admin_info = conninfo_to_dict(admin_url)
        self.assertNotEqual(admin_info.get('dbname'), 'digest', 'Never use the production-like digest database as recovery admin')
        for tool in ('age', 'age-keygen', 'pg_dump', 'pg_restore'):
            recovery.require_tool(tool)
        token = uuid4().hex[:16]
        source_name, target_name = 'industrial_ai_restore_source_'+token, 'industrial_ai_restore_target_'+token
        source_url = make_conninfo(**dict(admin_info, dbname=source_name))
        target_url = make_conninfo(**dict(admin_info, dbname=target_name))
        created = []
        with psycopg.connect(admin_url, autocommit=True) as admin, tempfile.TemporaryDirectory() as folder:
            try:
                for name in (source_name, target_name):
                    admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                    created.append(name)
                with psycopg.connect(source_url, autocommit=True) as source:
                    migrations = Path(__file__).resolve().parent/'prisma/migrations'
                    for migration in sorted(migrations.glob('*/migration.sql')):
                        source.execute(migration.read_text(encoding='utf-8'), prepare=False)
                    source.execute("INSERT INTO automation_events VALUES('recovery-test-event','recovery-test-issue')")
                    source.execute("INSERT INTO edition_revisions VALUES('recovery-test-revision','recovery-test-issue',1,'{}','{}',now())")
                    source.execute("SET TIME ZONE 'America/New_York'")
                    before = recovery.fingerprint(source)
                root = Path(folder)
                recovery.protect_windows_directory(root)
                identity = root/'restore-identity.txt'
                result = subprocess.run([recovery.require_tool('age-keygen'), '-o', str(identity)], capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0)
                identity.chmod(0o600)
                public = subprocess.run([recovery.require_tool('age-keygen'), '-y', str(identity)], capture_output=True, timeout=20)
                self.assertEqual(public.returncode, 0)
                recipient = public.stdout.decode().strip()
                offhost = root/'simulated-independent-storage'; offhost.mkdir(mode=0o700)
                budget_file = root/'budget.json'
                budget_file.write_text('{"limit":2,"requests":[]}', encoding='utf-8')
                backup = recovery.backup(source_url, recipient, 'test-local:'+str(offhost),
                    state_dir=root/'encrypted-state', state_file=budget_file, allow_test_transport=True)
                archive, manifest = Path(backup['remoteArchive']), Path(backup['remoteManifest'])
                self.assertTrue(archive.read_bytes().startswith(b'age-encryption.org/'))
                self.assertTrue(manifest.read_bytes().startswith(b'age-encryption.org/'))
                # Corruption must fail before opening the destination database.
                original_ciphertext = archive.read_bytes()
                archive.write_bytes(original_ciphertext[:-1] + bytes([original_ciphertext[-1] ^ 1]))
                try:
                    with patch.object(psycopg, 'connect', side_effect=AssertionError('No destination connection')):
                        with self.assertRaisesRegex(recovery.RecoveryError, 'integrity-checked manifest'):
                            recovery.restore(archive, identity, target_url, manifest)
                finally:
                    archive.write_bytes(original_ciphertext)
                # Read-only backup snapshots cannot mutate the source, even with a writable login.
                with recovery.source_snapshot(source_url) as (snapshot_db, _):
                    with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                        snapshot_db.execute("INSERT INTO automation_events VALUES('must-not-write','must-not-write')")
                # A relation-only emptiness check would miss functions/types that pg_restore could replace.
                with psycopg.connect(target_url, autocommit=True) as target:
                    target.execute('CREATE FUNCTION public.recovery_existing() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$')
                    with self.assertRaisesRegex(recovery.RecoveryError, 'not empty'):
                        recovery.restore(archive, identity, target_url, manifest)
                    target.execute('DROP FUNCTION public.recovery_existing()')
                    target.execute("CREATE TYPE public.recovery_existing AS ENUM ('test')")
                    with self.assertRaisesRegex(recovery.RecoveryError, 'not empty'):
                        recovery.restore(archive, identity, target_url, manifest)
                    target.execute('DROP TYPE public.recovery_existing')
                # A new restore host only needs downloaded ciphertext and its private recovery identity.
                state_output = root/target_name/'budget.json'
                restored = recovery.restore(archive, identity, target_url, manifest, state_output=state_output)
                self.assertTrue(restored['restored'])
                self.assertTrue(restored['budgetStateRestored'])
                self.assertEqual(state_output.read_bytes(), budget_file.read_bytes())
                with psycopg.connect(target_url, autocommit=True) as target:
                    target.execute("SET TIME ZONE 'Europe/Berlin'")
                    self.assertEqual(recovery.fingerprint(target), before)
                    with self.assertRaises(psycopg.errors.ObjectNotInPrerequisiteState):
                        target.execute('DELETE FROM edition_revisions')
                with self.assertRaises(recovery.RecoveryError):
                    recovery.restore(archive, identity, target_url, manifest)
                with self.assertRaises(recovery.RecoveryError):
                    recovery.restore(archive, identity, source_url, manifest)
                with psycopg.connect(source_url, autocommit=True) as source:
                    self.assertEqual(recovery.fingerprint(source), before)
                with psycopg.connect(target_url, autocommit=True) as target:
                    with self.assertRaises(psycopg.errors.ObjectNotInPrerequisiteState):
                        target.execute("DELETE FROM edition_revisions WHERE id='recovery-test-revision'")
                self.assertEqual(list(root.rglob('*.dump')), [])
            finally:
                # Only databases freshly created by this test and carrying its UUID are removed.
                for name in reversed(created):
                    assert re.fullmatch(r'industrial_ai_restore_(source|target)_'+token, name)
                    admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


if __name__ == '__main__':
    unittest.main()
