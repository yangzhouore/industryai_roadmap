"""Synthetic offline tests for real-source backfill date handling and replay."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.pipeline.ingest import backfill, publication_day


class BackfillTests(unittest.TestCase):
    def test_berlin_day_uses_publication_timestamp(self):
        article = {'publishedAt':'2026-10-31T23:30:00Z','eventAt':'2026-10-20T12:00:00Z'}
        self.assertEqual(publication_day(article), '2026-11-01')
        self.assertEqual(article['eventAt'], '2026-10-20T12:00:00Z')
        self.assertEqual(publication_day({'publishedAt':'2026-11-13T23:00:00Z'}), '2026-11-14')
        with self.assertRaisesRegex(ValueError, 'explicit timezone'):
            publication_day({'publishedAt':'2026-11-01T12:00:00'})

    def test_window_boundaries_replay_and_original_event_time(self):
        source = {'id':'synthetic-test','name':'Synthetic test source','homepage':'https://example.org/fixtures/',
                  'feed_url':'https://example.org/fixtures/feed','allowed_hosts':['example.org'],
                  'synthetic':True,'archive_feeds':['https://example.org/fixtures/archive']}
        def article(key, timestamp, event=None):
            return {'sourceId':source['id'],'name':source['name'],'url':'https://example.org/fixtures/'+key,
                    'title':'Synthetic '+key,'excerpt':'Synthetic excerpt '+key,'publishedAt':timestamp,
                    'eventAt':event,'timezone':'UTC','synthetic':True,'contentHash':key}
        records = [article('first','2026-10-31T23:30:00Z','2026-10-20T12:00:00Z'),
                   article('last','2026-11-13T22:59:59Z'),article('excluded','2026-11-13T23:00:00Z')]
        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder)/'test.sqlite')
            with patch('services.pipeline.ingest.load_registry',return_value=[source]), \
                 patch('services.pipeline.ingest.collect_source',side_effect=lambda *a,**kw:(deepcopy(records),[{'status':200}])):
                first = backfill('unused',database,'2026-11-01','2026-11-13')
                second = backfill('unused',database,'2026-11-01','2026-11-13')
            self.assertEqual(first['articlesInserted'],2)
            self.assertEqual(second['articlesInserted'],0)
            self.assertEqual(first['coverage']['2026-11-01'],1)
            self.assertEqual(first['coverage']['2026-11-13'],1)
            connection = sqlite3.connect(database)
            try:
                rows = connection.execute('SELECT event_at,raw_metadata FROM raw_articles ORDER BY canonical_url').fetchall()
                self.assertEqual(len(rows),2)
                self.assertEqual(rows[0][0],'2026-10-20T12:00:00Z')
                self.assertEqual(json.loads(rows[0][1])['backfillWindow']['timezone'],'Europe/Berlin')
                self.assertEqual(connection.execute("SELECT count(*) FROM pipeline_runs WHERE stage='collection_backfill' AND status='success'").fetchone()[0],2)
            finally:
                connection.close()

    def test_invalid_window_rejected_before_database_creation(self):
        with self.assertRaises(ValueError):
            backfill('unused','unused','2026-11-13','2026-11-01')
        with self.assertRaises(ValueError):
            backfill('unused','unused','2026-01-01','2026-11-13')

    def test_unapproved_archive_host_is_not_requested(self):
        source = {'id':'synthetic-test','name':'Synthetic test source','homepage':'https://example.org/fixtures/',
                  'feed_url':'https://example.org/fixtures/feed','allowed_hosts':['example.org'],
                  'synthetic':True,'archive_feeds':['https://other.example.org/feed']}
        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder)/'test.sqlite')
            with patch('services.pipeline.ingest.load_registry',return_value=[source]), \
                 patch('services.pipeline.ingest.collect_source',return_value=([],[{'status':200}])) as collector:
                result = backfill('unused',database,'2026-11-01','2026-11-13')
            self.assertEqual(collector.call_count,1)
            self.assertEqual(len(result['errors']),1)
            self.assertIn('outside reviewed source hosts',result['errors'][0]['error'])
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute('SELECT status FROM pipeline_runs').fetchone()[0],'partial')
            finally:
                connection.close()


if __name__ == '__main__':
    unittest.main()
