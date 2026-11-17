"""Prepare NEW private roles/database after explicit approval; never changes existing identities."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from dedicated_cluster import GUARD, psql_command

ROLES = ('industrial_owner', 'industrial_web', 'industrial_worker', 'industrial_backup')
SECRETS = ('INDUSTRIAL_OWNER_DB_PASSWORD', 'INDUSTRIAL_WEB_DB_PASSWORD',
           'INDUSTRIAL_WORKER_DB_PASSWORD', 'INDUSTRIAL_BACKUP_DB_PASSWORD')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provision', action='store_true')
    args = parser.parse_args(argv)
    if not args.provision:
        print('Dry check only; --provision after approval is required for new database/role creation.')
        return 0
    if os.name != 'posix' or os.geteuid() != 0:
        raise ValueError('Explicit provisioning must run as root on the target Ubuntu host')
    passwords = [os.environ.get(name, '') for name in SECRETS]
    if (any(len(value) < 24 or value.casefold() in {'digest', 'password', 'postgres', 'changeme'}
            or '\n' in value or '\r' in value for value in passwords) or len(set(passwords)) != len(SECRETS)):
        raise ValueError('Four strong, distinct role passwords are required in protected process environment variables')
    # Run psql with local peer authentication as postgres. Passwords are inherited
    # in the child environment and loaded with \getenv, never command arguments.
    command = psql_command()
    check = GUARD + "SELECT count(*) FROM pg_roles WHERE rolname IN ('industrial_owner','industrial_web','industrial_worker','industrial_backup');\nSELECT count(*) FROM pg_database WHERE datname='industrial_ai';\n"
    result = subprocess.run(command+['--tuples-only', '--no-align'], input=check, text=True,
                            capture_output=True, check=False)
    if result.returncode or result.stdout.split() != ['0', '0']:
        raise ValueError('Existing database/role or unavailable private cluster; nothing will be replaced')
    script = GUARD + '\n'.join('\\getenv password_' + str(i) + ' ' + name for i, name in enumerate(SECRETS))
    script += '\nBEGIN;\n'
    for i, role in enumerate(ROLES):
        script += f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'password_{i}';\n"
    script += 'COMMIT;\nCREATE DATABASE industrial_ai OWNER industrial_owner;\n'
    script += 'REVOKE ALL ON DATABASE industrial_ai FROM PUBLIC;\n'
    script += 'GRANT CONNECT ON DATABASE industrial_ai TO industrial_web,industrial_worker,industrial_backup;\n'
    result = subprocess.run(command, input=script, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Private database provisioning failed; inspect private server logs, never replace existing roles automatically')
    print('Created new distinct roles and private database. Apply migrations as industrial_owner, then explicit grants.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        print('Database provisioning refused or failed; credentials withheld.', file=sys.stderr)
        raise SystemExit(1)
