"""Build/seal a new checkout. No selection, service activation or DB operation."""
import argparse
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
sys.dont_write_bytecode = True
from preflight import check


def build_environment(env):
    """Builds receive the public origin, never runtime database/API credentials."""
    return {'PATH':'/usr/bin:/bin', 'HOME':'/var/lib/industrial-ai/build',
            'NODE_ENV':'production', 'NEXT_TELEMETRY_DISABLED':'1',
            'DATA_MODE':'database', 'SITE_URL':env['SITE_URL']}


def load_environment(path):
    metadata = path.lstat()
    if path.is_symlink() or not path.is_file() or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError('Environment must be a root-owned regular 0600 file')
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise ValueError('Invalid environment field')
        parsed = shlex.split(value, comments=False)
        if len(parsed) != 1:
            raise ValueError('Every deployment field requires one non-empty value')
        values[key] = parsed[0]
    return values


def own_tree(directory, uid, gid, seal=False):
    for base, dirs, files in os.walk(directory, followlinks=False):
        for path in [Path(base), *[Path(base)/f for f in files],
                     *[Path(base)/d for d in dirs if (Path(base)/d).is_symlink()]]:
            os.chown(path, uid, gid, follow_symlinks=False)
            if not path.is_symlink():
                executable = path.is_dir() or bool(path.stat().st_mode & 0o111)
                path.chmod(0o750 if executable else 0o640)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare')
    args = parser.parse_args(argv)
    if not args.prepare:
        print('Read-only check; explicit --prepare NEW_RELEASE is required. No release selected.')
        return 0
    if os.name != 'posix' or os.geteuid() != 0:
        raise ValueError('Preparation requires root on the separately approved target')
    import pwd
    release = Path(args.prepare).resolve()
    if not re.fullmatch(r'/srv/industrial-ai/releases/[a-f0-9]{40}', str(release)) or not release.is_dir():
        raise ValueError('A new full-commit checkout under /srv/industrial-ai/releases is required')
    for name in ('.industrial-ai-prepared', '.venv', 'artifacts', '.env', '.env.local', 'apps/web/.env.local'):
        if (release/name).exists() or (release/name).is_symlink():
            raise ValueError('Release contains existing build state or local secrets')
    current = Path('/srv/industrial-ai/current')
    if current.exists() and current.resolve() == release:
        raise ValueError('Never rebuild or change permissions on the currently selected release')
    git = ['git','--no-pager','-c','safe.directory='+str(release),'-c','core.fsmonitor=false',
           '-c','core.hooksPath=/dev/null','-C',str(release)]
    if subprocess.check_output(git+['status','--porcelain','--untracked-files=all']):
        raise ValueError('Tracked checkout must be clean and contain no ordinary untracked files')
    if subprocess.check_output(git+['ls-files','--others','-z']):
        raise ValueError('Fresh release must contain no ignored/untracked files, including local secrets or caches')
    for base, dirs, files in os.walk(release, followlinks=False):
        dirs[:] = [name for name in dirs if name not in {'.git','node_modules'}]
        if any(name.startswith('.env') and not name.endswith('.example') for name in files):
            raise ValueError('Environment secret variants are forbidden anywhere in a release checkout')
    revision = subprocess.check_output(['git','-c','safe.directory='+str(release),'-C',str(release),'rev-parse','HEAD'], text=True).strip()
    if revision != release.name:
        raise ValueError('Checkout does not match approved commit directory')
    env = load_environment(Path('/etc/industrial-ai/web.env'))
    check('web', env, release)
    builder, reader = pwd.getpwnam('industrial-build'), pwd.getpwnam('industrial-web')
    own_tree(release, builder.pw_uid, builder.pw_gid)
    build_env = build_environment(env)
    def run(command):
        subprocess.run(['runuser','-u','industrial-build','--',*command], cwd=release, env=build_env, check=True)
    for command in (['npm','ci','--include=dev'], ['npm','run','db:generate'], ['npm','run','build'],
                    ['python3.12','-m','venv',str(release/'.venv')],
                    [str(release/'.venv/bin/python'),'-m','pip','install','-r','services/pipeline/requirements.txt']):
        run(command)
    frozen = subprocess.check_output(['runuser','-u','industrial-build','--',str(release/'.venv/bin/python'),'-m','pip','freeze'], cwd=release, env=build_env, text=True)
    # Package lifecycle hooks must not silently alter the approved application source.
    subprocess.run(git+['fsck','--strict','--no-reflogs'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(git+['diff','--no-ext-diff','--no-textconv','--exit-code',revision,'--'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(git+['diff','--cached','--no-ext-diff','--no-textconv','--exit-code',revision,'--'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (release/'python-resolved.txt').write_text(frozen)
    (release/'artifacts').symlink_to('/var/lib/industrial-ai/artifacts', target_is_directory=True)
    cache = release/'apps/web/.next/cache'
    if cache.is_symlink():
        raise ValueError('Web cache must be inside the release')
    cache.mkdir(parents=True, exist_ok=True)
    (release/'.industrial-ai-prepared').write_text(revision+'\n')
    own_tree(release, 0, builder.pw_gid, seal=True)
    own_tree(cache, reader.pw_uid, reader.pw_gid)
    print('Prepared/sealed new release and web-owned cache. No current/venv symlink changed; no service started.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Release preparation refused or failed; credentials withheld.', file=sys.stderr)
        raise SystemExit(1)
