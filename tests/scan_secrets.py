"""Scan exact Git-tracked blobs; report filenames only, never matching secret text."""
import os
from pathlib import PurePosixPath
import re
import subprocess

PATTERNS = (
    rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}',
    rb'(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{25,}',
    rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
    rb'AGE-SECRET-KEY-[A-Z0-9]{20,}',
    rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----',
)


def forbidden_path(name):
    path = PurePosixPath(name)
    filename = path.name.casefold()
    return (any(part in {'artifacts', 'data', 'node_modules', '.next', '__pycache__'} for part in path.parts)
            or ((path.name.startswith('.env') or path.name.endswith('.env') or '.env.' in path.name)
                and not path.name.endswith('.example'))
            or filename in {'rclone.conf', 'pgpass', '.pgpass', '.pg_service.conf'}
            or (filename.endswith('.json') and filename.startswith(('credentials', 'service-account')))
            or path.suffix.lower() in {'.age', '.agekey'}
            or path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.sqlite', '.db', '.dump', '.backup'})


def main():
    git = ['git', '-c', 'safe.directory=' + os.getcwd().replace('\\', '/')]
    names = subprocess.check_output(git+['ls-files', '-z']).decode().strip('\0').split('\0')
    key = os.environ.get('OPENAI_API_KEY', '').encode()
    findings = []
    for name in filter(None, names):
        data = subprocess.check_output(git+['show', ':'+name])
        if forbidden_path(name) or (key and key in data) or any(re.search(pattern, data) for pattern in PATTERNS):
            findings.append(name)
    if findings:
        print('Secret/path scan findings (filenames only):')
        for name in findings:
            print(name)
        return 1
    print(f'Secret/path scan passed: {len(names)} tracked files; zero findings')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
