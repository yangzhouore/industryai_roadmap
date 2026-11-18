"""Verify tracker DDL beside the existing news schema on a disposable PostgreSQL database."""

import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg import errors, sql


MIGRATIONS = Path(__file__).parent / 'prisma' / 'migrations'
TRACKER = '20261118000000_industrial_ai_tracker'
DATABASE = os.getenv('TEST_DATABASE_URL')

REVISIONS = """
    INSERT INTO tracker_milestone_revisions(id, milestone_id, revision, issue_id, issue_hash, story_id, stage)
    VALUES (%s, 'milestone-demo', %s, 'issue-demo', %s, 'issue-demo:story-demo', %s)
"""

EVIDENCE = """
    INSERT INTO tracker_evidence(revision_id, source_key, raw_article_id, kind, published_at, event_at,
                                 publisher, canonical_url, source_timezone)
    VALUES (%s, %s, 'article-demo', 'other', '2026-11-12T12:00Z', '2026-11-09T09:00Z',
            'Synthetic evidence', 'https://example.org/fixtures/tracker', 'UTC')
"""


@unittest.skipUnless(DATABASE, 'TEST_DATABASE_URL must identify a disposable PostgreSQL target')
class TrackerMigrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(DATABASE, autocommit=True)
        self.addCleanup(self.conn.close)
        self.schema = sql.Identifier(f'tracker_migration_test_{uuid4().hex}')
        self.conn.execute(sql.SQL('CREATE SCHEMA {}').format(self.schema))
        self.addCleanup(self.conn.execute, sql.SQL('DROP SCHEMA {} CASCADE').format(self.schema))
        self.conn.execute(sql.SQL('SET search_path TO {}, public').format(self.schema))
        for migration in sorted(MIGRATIONS.glob('*/migration.sql')):
            if migration.parent.name < TRACKER:
                self.conn.execute(migration.read_text(encoding='utf-8'))
        self.conn.execute("""
            INSERT INTO issues(id, slug, issue_date, state, validated, content, published_at)
            VALUES ('issue-demo', 'issue-demo', '2026-11-12', 'published', true,
                    '{"synthetic":true,"preserved":true}', '2026-11-12T12:00Z');
            INSERT INTO sources VALUES ('source-demo', 'Synthetic evidence', 'https://example.org', NULL,
                                        'fixture', true, '{}');
            INSERT INTO raw_articles(id, source_id, canonical_url, title, body_excerpt, published_at, event_at,
                                     source_timezone, content_hash, raw_metadata)
            VALUES ('article-demo', 'source-demo', 'https://example.org/fixtures/tracker', 'Synthetic evidence',
                    'Private fixture text', '2026-11-12T12:00Z', '2026-11-09T09:00Z', 'UTC', 'demo', '{}');
            INSERT INTO digest_stories(id, issue_id, position, kind, structured_content, evidence_status)
            VALUES ('issue-demo:story-demo', 'issue-demo', 0, 'feature', '{}', 'synthetic');
        """)
        self.original = self.snapshot()
        self.conn.execute((MIGRATIONS / TRACKER / 'migration.sql').read_text(encoding='utf-8'))

    def snapshot(self):
        return self.conn.execute("""
            SELECT row_to_json(i), row_to_json(a), row_to_json(s)
            FROM issues i CROSS JOIN raw_articles a CROSS JOIN digest_stories s
        """).fetchone()

    def seed_parents(self):
        self.conn.execute("""
            INSERT INTO tracker_projects(id) VALUES ('project-demo') ON CONFLICT DO NOTHING;
            INSERT INTO tracker_milestones(id, project_id) VALUES ('milestone-demo', 'project-demo')
                ON CONFLICT DO NOTHING;
            INSERT INTO tracker_companies VALUES ('demo-company', 'Demo company', '示例公司') ON CONFLICT DO NOTHING;
            INSERT INTO tracker_company_aliases VALUES ('demo co', 'demo-company') ON CONFLICT DO NOTHING;
            INSERT INTO tracker_technologies VALUES ('demo-technology', 'Demo technology', '示例技术')
                ON CONFLICT DO NOTHING;
            INSERT INTO tracker_technology_aliases VALUES ('demo tech', 'demo-technology') ON CONFLICT DO NOTHING;
        """)

    def test_additive_migration_and_seed_replay(self):
        self.assertEqual(self.snapshot(), self.original)
        self.seed_parents()
        self.seed_parents()
        self.assertEqual(self.conn.execute("SELECT count(*) FROM tracker_milestones").fetchone(), (1,))
        self.assertEqual(self.conn.execute("SELECT company_id FROM tracker_company_aliases").fetchone(), ('demo-company',))
        self.assertEqual(self.conn.execute("SELECT technology_id FROM tracker_technology_aliases").fetchone(), ('demo-technology',))
        with self.assertRaises(errors.UniqueViolation):
            self.conn.execute("INSERT INTO tracker_company_aliases VALUES ('demo co', 'demo-company')")
        self.assertEqual(self.snapshot(), self.original)

    def test_revisions_keep_provenance_and_seal_their_children(self):
        self.seed_parents()
        with self.conn.transaction():
            with self.conn.transaction():
                self.conn.execute(REVISIONS, ('rev-one', 1, 'a' * 64, 'research'))
            self.conn.execute(EVIDENCE, ('rev-one', 'source-demo'))
            with self.assertRaises(errors.UniqueViolation), self.conn.transaction():
                self.conn.execute(EVIDENCE, ('rev-one', 'second-alias-of-same-article'))
            self.conn.execute("INSERT INTO tracker_revision_companies VALUES ('rev-one', 'demo-company')")
        self.conn.execute(REVISIONS, ('rev-two', 2, 'b' * 64, 'prototype'))
        with self.assertRaises(errors.UniqueViolation):
            self.conn.execute(REVISIONS, ('rev-duplicate', 2, 'b' * 64, 'prototype'))
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(REVISIONS, ('rev-invalid-hash', 3, 'invalid', 'pilot'))
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(REVISIONS, ('rev-invalid-stage', 3, 'c' * 64, 'unknown'))
        for statement in (
            "UPDATE tracker_milestone_revisions SET withdrawn = true WHERE id = 'rev-one'",
            "DELETE FROM tracker_milestone_revisions WHERE id = 'rev-two'",
            "UPDATE tracker_evidence SET event_at = published_at WHERE revision_id = 'rev-one'",
            "DELETE FROM tracker_revision_companies WHERE revision_id = 'rev-one'",
            "INSERT INTO tracker_revision_technologies VALUES ('rev-one', 'demo-technology')",
            "INSERT INTO tracker_revision_companies VALUES ('rev-two', 'demo-company')",
        ):
            with self.subTest(statement=statement), self.assertRaises(errors.ObjectNotInPrerequisiteState):
                self.conn.execute(statement)
        with self.assertRaises(errors.ObjectNotInPrerequisiteState):
            self.conn.execute(EVIDENCE, ('rev-two', 'late-source'))
        self.conn.execute("DELETE FROM digest_stories WHERE id = 'issue-demo:story-demo'")
        self.assertEqual(self.conn.execute("""
            SELECT issue_hash, story_id, stage FROM tracker_milestone_revisions ORDER BY revision
        """).fetchall(), [('a' * 64, 'issue-demo:story-demo', 'research'),
                        ('b' * 64, 'issue-demo:story-demo', 'prototype')])
        self.assertEqual(self.conn.execute("""
            SELECT published_at > event_at, canonical_url FROM tracker_evidence
        """).fetchone(), (True, 'https://example.org/fixtures/tracker'))
