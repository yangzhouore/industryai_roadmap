"""Maintain tracker associations locally from previously published editions."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

from .manifest import Catalog, TrackerError, identifier, load_changes
from .store import apply_changes, list_editions, list_stories, milestone_history


class TrackerParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Tracker arguments refused. Use --help.\n')


def main(argv=None):
    parser = TrackerParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--input', type=Path, help='Apply an explicit private version 1 tracker manifest.')
    options.add_argument('--list-editions', action='store_true', help='List published real edition IDs, slugs and dates.')
    options.add_argument('--list-stories', metavar='ISSUE_ID', help='Show edition hash and only story and source metadata.')
    options.add_argument('--milestone-history', metavar='MILESTONE_ID', help='List immutable tracker revision and citation IDs.')
    args = parser.parse_args(argv)
    try:
        changes = catalog = None
        if args.input is not None:
            catalog = Catalog.load()
            changes = load_changes(args.input, catalog)
        if args.list_stories is not None and not identifier(args.list_stories):
            raise TrackerError('Issue identifier is invalid.')
        if args.milestone_history is not None and not re.fullmatch(r'milestone-[0-9a-f]{24}', args.milestone_history):
            raise TrackerError('Milestone identifier is invalid.')
        dsn = os.environ.get('DATABASE_URL', '')
        if not dsn.startswith(('postgresql://', 'postgres://')):
            raise TrackerError('Set DATABASE_URL to a configured PostgreSQL connection in your environment.')

        import psycopg
        from psycopg.rows import dict_row

        connection_options = {} if changes is not None else {'options': '-c default_transaction_read_only=on'}
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10, row_factory=dict_row, **connection_options) as db:
            if changes is not None:
                result = {'changes': apply_changes(db, catalog, changes)}
            elif args.list_editions:
                result = {'editions': list_editions(db)}
            elif args.milestone_history:
                result = milestone_history(db, args.milestone_history)
            else:
                result = list_stories(db, args.list_stories)
        print(json.dumps(result, indent=2))
        return 0
    except TrackerError as error:
        print(str(error), file=sys.stderr)
    except ImportError:
        print('Tracker requires the installed pipeline PostgreSQL dependencies.', file=sys.stderr)
    except Exception:
        print('Tracker operation failed. PostgreSQL and source details were withheld.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
