"""Real PostgreSQL migration/publication checks in disposable per-test schemas.

Set TEST_DATABASE_URL to a local test database owned by a role allowed to create
schemas/extensions. No application tables outside the isolated schemas are changed.
"""
import copy
import json
import os
from pathlib import Path
import unittest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, quote
from uuid import uuid4
from services.pipeline.editorial import prepare_issue
from services.pipeline.store import Store

ROOT = Path(__file__).resolve().parents[1]
DATABASE = os.getenv('TEST_DATABASE_URL', '')


@unittest.skipUnless(DATABASE.startswith(('postgresql://', 'postgres://')), 'TEST_DATABASE_URL required')
class PostgresPublicationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.admin = psycopg.connect(DATABASE, autocommit=True)
        self.schema = 'digest_test_' + uuid4().hex
        self.addCleanup(self.cleanup_schema)
        self.admin.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public')
        self.admin.execute('CREATE SCHEMA ' + self.schema)
        parts = urlsplit(DATABASE)
        params = [(k,v) for k,v in parse_qsl(parts.query) if k != 'options']
        params.append(('options', '-c search_path=' + self.schema + ',public'))
        self.location = urlunsplit(parts._replace(query=urlencode(params, quote_via=quote)))
        self.store = Store(self.location)
        migration = ROOT / 'packages/db/prisma/migrations/20261112000000_initial/migration.sql'
        self.store.db.execute(migration.read_text(encoding='utf-8'), prepare=False)
        self.issues = json.loads((ROOT / 'packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))

    def cleanup_schema(self):
        if hasattr(self, 'store'):
            self.store.close()
        self.admin.execute('DROP SCHEMA IF EXISTS ' + self.schema + ' CASCADE')
        self.admin.close()

    def test_migration_and_evidence_replay(self):
        for issue in self.issues:
            draft = prepare_issue(issue)
            self.assertTrue(self.store.publish(draft))
            self.assertFalse(self.store.publish(draft))
        for table, expected in [('issues',3), ('raw_articles',9), ('digest_stories',9),
                                ('story_clusters',9), ('scores',9), ('story_citations',9),
                                ('translations',18), ('entities',3), ('story_entity_links',9)]:
            count = self.store.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            self.assertEqual(count, expected, table)
        self.store.log_run('fixture','success',{'issues':3})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM pipeline_runs').fetchone()[0],1)

    def test_collection_replay_persists_candidates_without_publication(self):
        from services.pipeline.ingest import ingest
        self.assertEqual(ingest(database=self.location)['articlesInserted'], 2)
        self.assertEqual(ingest(database=self.location)['articlesInserted'], 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM raw_articles').fetchone()[0], 2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM article_cluster_links').fetchone()[0], 2)
        self.assertEqual(self.store.published(), [])

    def test_publish_read_publish_persists_after_reopen(self):
        self.store.publish(prepare_issue(self.issues[0]))
        self.assertEqual(len(self.store.published()), 1)
        self.store.publish(prepare_issue(self.issues[1]))
        self.store.close()
        self.store = Store(self.location)
        self.assertEqual(len(self.store.published()), 2)

    def test_evidence_failure_rolls_back_both_locales(self):
        original = self.store.execute

        def fail_translation(query, values=()):
            result = original(query, values)
            if 'INSERT INTO translations' in query:
                raise RuntimeError('injected translation failure')
            return result

        self.store.execute = fail_translation
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.store.publish(prepare_issue(self.issues[0]))
        self.store.execute = original
        self.assertEqual(self.store.published(), [])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM raw_articles').fetchone()[0],0)
        self.assertTrue(self.store.publish(prepare_issue(self.issues[0])))

    def test_database_constraints_block_partial_publication(self):
        import psycopg
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.store.db.execute("INSERT INTO issues(id,slug,issue_date,state,validated,content) VALUES('bad','bad','2026-11-15','published',false,'{}')")
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.store.db.execute("INSERT INTO translations(story_id,locale,title,summary,structured_body,validation_state) VALUES('missing','en','x','x','{}','validated')")
        self.assertEqual(self.store.published(), [])

    def test_changed_canonical_evidence_rolls_back_new_edition(self):
        self.store.publish(prepare_issue(self.issues[0]))
        changed = copy.deepcopy(self.issues[0])
        changed.update(id='changed-issue',slug='2026-11-13',date='2026-11-13')
        changed['sources'][0]['excerpt']['en'] = 'A changed synthetic statement about inspection.'
        changed['sources'][0]['excerpt']['zh'] = '关于检测的另一条模拟陈述。'
        changed['stories'][0]['summary'] = copy.deepcopy(changed['sources'][0]['excerpt'])
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.store.publish(prepare_issue(changed))
        self.assertEqual(len(self.store.published()),1)


if __name__ == '__main__':
    unittest.main()
