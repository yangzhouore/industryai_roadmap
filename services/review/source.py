"""Only read-only PostgreSQL queries; no migration, publication, seed or backfill."""
import os
import re
from .security import ROOT, ReviewError, read_private


def source_dsn(environment='DATABASE_URL'):
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', environment):
        raise ReviewError('Use a configured database environment-variable name')
    value = os.environ.get(environment)
    if value:
        return value
    if environment == 'DATABASE_URL' and (ROOT/'.env.local').is_file():
        for line in read_private(ROOT/'.env.local', 65536).decode('utf-8-sig').splitlines():
            if line.strip().startswith('DATABASE_URL='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    raise ReviewError('Private read-only source connection is not configured')


def source_editions(dsn, issue_id=None):
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=10, options='-c default_transaction_read_only=on') as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            if db.execute('SHOW transaction_read_only').fetchone()[0] != 'on':
                raise ReviewError('Source connection is not read-only')
            if issue_id is None:
                return [{'id': row[0], 'date': row[1], 'title': row[2]} for row in db.execute("SELECT id,issue_date,content->'title' FROM issues WHERE state='published' AND validated AND content->>'synthetic'='false' ORDER BY issue_date,id")]
            rows = db.execute("SELECT content FROM issues WHERE id=%s AND state='published' AND validated AND content->>'synthetic'='false'", (issue_id,)).fetchall()
            if len(rows) != 1:
                raise ReviewError('A unique published real source edition is required')
            return rows[0][0]
    except ReviewError:
        raise
    except Exception:
        raise ReviewError('Read-only source unavailable; connection details withheld') from None
