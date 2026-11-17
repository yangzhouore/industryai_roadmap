"""Grant application privileges after migrations; requires explicit local administrator action."""
import argparse
import os
import subprocess
import sys
from dedicated_cluster import GUARD, psql_command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    if not parser.parse_args(argv).apply:
        print('Dry check only; --apply is required after reviewed migrations.')
        return 0
    if os.name != 'posix' or os.geteuid() != 0:
        raise ValueError('Explicit grants require local root/peer administration')
    script = GUARD + '''BEGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO industrial_web,industrial_worker,industrial_backup;
GRANT SELECT ON issues TO industrial_web;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO industrial_worker;
REVOKE INSERT,UPDATE ON _prisma_migrations FROM industrial_worker;
REVOKE UPDATE ON edition_revisions FROM industrial_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO industrial_backup;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO industrial_worker;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO industrial_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE industrial_owner IN SCHEMA public GRANT SELECT,INSERT,UPDATE ON TABLES TO industrial_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE industrial_owner IN SCHEMA public GRANT SELECT ON TABLES TO industrial_backup;
COMMIT;
'''
    command = [value if value != '--dbname=postgres' else '--dbname=industrial_ai' for value in psql_command()]
    result = subprocess.run(command, input=script,
        text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Grant transaction failed; private database diagnostics required')
    print('Granted read-only web/backup access and bounded worker writes; no public DB access was enabled.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        print('Privilege preparation refused or failed; credentials withheld.', file=sys.stderr)
        raise SystemExit(1)
