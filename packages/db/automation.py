"""Automation persistence. PostgreSQL requires an explicit additive migration."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


SQLITE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS automation_runs (
 id TEXT PRIMARY KEY, issue_date TEXT NOT NULL, mode TEXT NOT NULL,
 status TEXT NOT NULL, stage TEXT NOT NULL, started_at TEXT NOT NULL,
 ended_at TEXT, stats TEXT NOT NULL DEFAULT '{}', error TEXT);
CREATE INDEX IF NOT EXISTS automation_runs_date ON automation_runs(issue_date,started_at);
CREATE TABLE IF NOT EXISTS api_requests (
 id TEXT PRIMARY KEY, month TEXT NOT NULL, run_id TEXT, stage TEXT NOT NULL,
 model TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=0),
 status TEXT NOT NULL CHECK(status IN ('reserved','measured')),
 reserved_usd TEXT NOT NULL, estimated_usd TEXT NOT NULL, usage TEXT,
 response_id TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS api_requests_month ON api_requests(month,created_at);
CREATE TABLE IF NOT EXISTS automation_events (
 event_key TEXT PRIMARY KEY, issue_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS automation_cache (
 cache_key TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL);
'''


class AutomationStore:
    def __init__(self, location):
        self.postgres = str(location).startswith(('postgresql://', 'postgres://'))
        if self.postgres:
            import psycopg
            self.db = psycopg.connect(location, autocommit=True)
        else:
            Path(location).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(location, timeout=30, isolation_level=None)
            self.db.execute('PRAGMA busy_timeout=30000')
            self.db.executescript(SQLITE_SCHEMA)

    def execute(self, query, args=()):
        return self.db.execute(query.replace('?', '%s') if self.postgres else query, args)

    def json_value(self, value):
        if self.postgres:
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    @contextmanager
    def transaction(self):
        if self.postgres:
            with self.db.transaction():
                yield
        else:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
            else:
                self.db.execute('COMMIT')

    def start_run(self, issue_date, mode):
        identifier = uuid4().hex
        self.execute('''INSERT INTO automation_runs
            (id,issue_date,mode,status,stage,started_at,stats) VALUES(?,?,?,?,?,?,?)''',
            (identifier, issue_date, mode, 'running', 'start',
             datetime.now(timezone.utc).isoformat(), self.json_value({})))
        return identifier

    def finish_run(self, identifier, status, stage, stats, error=None):
        self.execute('''UPDATE automation_runs SET status=?,stage=?,stats=?,error=?,ended_at=?
            WHERE id=?''', (status, stage, self.json_value(stats), error,
                           datetime.now(timezone.utc).isoformat(), identifier))

    def runs(self, limit=30):
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError('Run limit must be between 1 and 1000')
        cursor = self.execute('''SELECT id,issue_date,mode,status,stage,started_at,ended_at,stats,error
            FROM automation_runs ORDER BY started_at DESC,id DESC LIMIT ?''', (limit,))
        fields = ('id', 'issue_date', 'mode', 'status', 'stage', 'started_at', 'ended_at', 'stats', 'error')
        records = []
        for row in cursor.fetchall():
            record = dict(zip(fields, row))
            if isinstance(record['stats'], str):
                record['stats'] = json.loads(record['stats'])
            for field in ('started_at', 'ended_at'):
                if hasattr(record[field], 'isoformat'):
                    record[field] = record[field].isoformat()
            records.append(record)
        return records

    def close(self):
        self.db.close()
