"""Real registry contracts and HTTP incremental replay without network-dependent tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from services.pipeline.collectors import FeedClient
from services.pipeline.extraction import parse_feed
from services.pipeline.ingest import ArticleStore, ROOT, collect_source, ingest, load_registry


class RealIngestionTests(unittest.TestCase):
    def test_real_registry_has_independent_reviewed_sources(self):
        sources = load_registry(ROOT / 'config/sources.yaml')
        self.assertGreaterEqual(len(sources), 5)
        self.assertGreaterEqual(len({source['homepage'].split('/')[2] for source in sources}), 5)
        for source in sources:
            self.assertFalse(source['synthetic'])
            self.assertEqual(source['policy_scope'], 'local_noncommercial')
            self.assertFalse(source['redistribution_permitted'])
            self.assertTrue(source['policy_evidence'])

    def test_original_title_author_language_and_date_retained(self):
        payload = b'<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><language>en</language><item><title>Inspection &amp; uncertainty</title><dc:creator>Research author</dc:creator><link>https://news.mit.edu/test</link><pubDate>Fri, 13 Nov 2026 00:00:00 -0500</pubDate><description>Feed description</description></item></channel></rss>'
        article = parse_feed(payload, 'unit', 'Unit')[0]
        self.assertEqual(article['originalTitle'], 'Inspection & uncertainty')
        self.assertEqual(article['authors'], ['Research author'])
        self.assertEqual(article['language'], 'en')
        self.assertEqual(article['publishedAt'], '2026-11-13T05:00:00Z')
        self.assertIn('-0500', article['sourcePublishedAt'])
        self.assertIsNone(article['eventAt'])

    def test_conditional_headers_and_304_are_feed_only(self):
        def connection(status, payload, headers):
            response = Mock(status=status)
            response.read.return_value = payload
            response.getheader.side_effect = lambda key, default=None: headers.get(key, default)
            client = Mock()
            client.getresponse.return_value = response
            return client
        robots = connection(200, b'User-agent: *\nAllow: /', {})
        feed = connection(304, b'', {'ETag': '"unchanged"'})
        client = FeedClient({'news.mit.edu'})
        with patch('services.pipeline.collectors.validate_url', side_effect=lambda url, hosts: (url, ['93.184.216.34'])), \
             patch('services.pipeline.collectors._PinnedHTTPS', side_effect=[robots, feed]), \
             patch('services.pipeline.collectors.time.sleep'):
            result = client.fetch('https://news.mit.edu/feed', feed_permitted=True, validators={'etag': '"unchanged"'})
        self.assertEqual(result, b'')
        self.assertTrue(client.not_modified)
        self.assertNotIn('If-None-Match', robots.request.call_args.kwargs['headers'])
        self.assertEqual(feed.request.call_args.kwargs['headers']['If-None-Match'], '"unchanged"')
        self.assertEqual([row['status'] for row in client.audit], [200, 304])

    def test_missing_live_policy_evidence_is_rejected(self):
        source = load_registry(ROOT / 'config/sources.yaml')[0]
        source.pop('policy_evidence')
        with tempfile.TemporaryDirectory() as folder:
            registry = Path(folder) / 'registry.json'
            registry.write_text(json.dumps({'sources': [source]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'dated policy evidence'):
                load_registry(registry)

    def test_empty_feed_is_not_counted_as_working_source(self):
        source = load_registry(ROOT / 'config/sources.yaml')[0]
        client = Mock(not_modified=False, response_metadata={}, audit=[{'status': 200}])
        client.fetch.return_value = b'<rss><channel/></rss>'
        with patch('services.pipeline.ingest.FeedClient', return_value=client):
            with self.assertRaisesRegex(ValueError, 'no usable article'):
                collect_source(source, fixture=False)

    def test_cached_run_keeps_existing_articles_and_records_audit(self):
        source = load_registry(ROOT / 'config/sources.yaml')[0]
        source['http_cache'] = {'etag': '"known"'}
        client = Mock(not_modified=True, response_metadata={'status':304,'etag':'"known"'}, audit=[{'status':304}])
        client.fetch.return_value = b''
        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder) / 'data.sqlite')
            registry = Path(folder) / 'sources.json'
            registry.write_text(json.dumps({'sources':[source]}), encoding='utf-8')
            store = ArticleStore(database)
            store.persist_source(source, [])
            store.close()
            with patch('services.pipeline.ingest.FeedClient', return_value=client):
                result = ingest(registry, database, 'live')
            self.assertEqual(result['notModified'], 1)
            self.assertEqual(result['articlesInserted'], 0)
            self.assertEqual(result['sourcesSucceeded'], 1)
            self.assertEqual(client.fetch.call_args.kwargs['validators']['etag'], '"known"')


if __name__ == '__main__':
    unittest.main()
