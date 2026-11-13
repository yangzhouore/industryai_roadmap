import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from services.pipeline.ingest import ArticleStore, FIXTURES, ingest, load_registry

class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db = str(self.folder/'ingest.sqlite')
    def query(self, sql):
        connection = sqlite3.connect(self.db)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()
    def registry(self):
        data = json.loads((FIXTURES/'registry.json').read_text(encoding='utf-8'))
        (self.folder/'feed.xml').write_bytes((FIXTURES/'feed.xml').read_bytes())
        path = self.folder/'registry.json'
        path.write_text(json.dumps(data),encoding='utf-8')
        return path,data
    def test_replay_and_clusters(self):
        self.assertEqual(ingest(database=self.db)['articlesInserted'],2)
        self.assertEqual(ingest(database=self.db)['articlesInserted'],0)
        for table in ('raw_articles','story_clusters','article_cluster_links'):
            self.assertEqual(self.query('SELECT COUNT(*) FROM '+table)[0][0],2)
        self.assertEqual(self.query("SELECT COUNT(*) FROM pipeline_runs WHERE status='success'")[0][0],2)
        self.assertEqual(self.query("SELECT COUNT(*) FROM sqlite_master WHERE name='issues'")[0][0],0)
    def test_partial_failure_is_audited(self):
        path,data = self.registry()
        data['sources'].append(dict(data['sources'][0],id='bad-feed',fixture_file='bad.xml'))
        (self.folder/'bad.xml').write_text('<rss><malformed>',encoding='utf-8')
        path.write_text(json.dumps(data),encoding='utf-8')
        result = ingest(path,self.db)
        self.assertEqual((result['sourcesSucceeded'],result['sourcesFailed']),(1,1))
        self.assertEqual(self.query('SELECT status FROM pipeline_runs')[0][0],'partial')

    def test_publication_day_is_not_inferred_as_candidate_event_day(self):
        ingest(database=self.db)
        self.assertTrue(all(row[0] is None for row in self.query('SELECT event_date FROM story_clusters')))
        self.assertTrue(all(row[0] for row in self.query('SELECT published_at FROM raw_articles')))
    def test_registry_failure_audit(self):
        path,data = self.registry()
        data['sources'].append(data['sources'][0])
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            ingest(path,self.db)
        self.assertEqual(self.query('SELECT status FROM pipeline_runs')[0][0],'failed')
    def test_transaction_rollback(self):
        original = ArticleStore.execute
        def broken(store,sql,args=()):
            if 'INSERT INTO story_clusters' in sql:
                raise sqlite3.IntegrityError('injected failure')
            return original(store,sql,args)
        with patch.object(ArticleStore,'execute',broken):
            self.assertEqual(ingest(database=self.db)['sourcesFailed'],1)
        self.assertEqual(self.query('SELECT COUNT(*) FROM raw_articles')[0][0],0)
    def test_fixture_path_boundary(self):
        path,data = self.registry()
        data['sources'][0]['fixture_file'] = '../outside.xml'
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'within registry'):
            load_registry(path,fixture=True)
    def test_unreviewed_source_rejected(self):
        path,data = self.registry()
        data['sources'][0].update(synthetic=False,policy_reviewed=False)
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'reviewed'):
            load_registry(path,fixture=False)
    def test_no_network(self):
        with patch('services.pipeline.ingest.FeedClient',side_effect=AssertionError('network used')):
            self.assertEqual(ingest(database=self.db)['articlesInserted'],2)
