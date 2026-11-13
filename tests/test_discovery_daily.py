"""Offline archive diagnostics and cross-edition evidence suppression."""
import copy
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.pipeline.collectors.discovery import ROOT, main, probe_archives, source_inventory
from services.pipeline.dedup import suppress_previously_published


class DailyDiscoveryTests(unittest.TestCase):
    def test_inventory_includes_enabled_and_unavailable_sources(self):
        inventory = source_inventory(ROOT / 'config/sources.yaml')
        self.assertEqual(inventory['counts']['readySources'], 6)
        self.assertEqual(inventory['counts']['disabledSources'], 4)
        self.assertFalse(inventory['blockedSources'])
        self.assertTrue(all(source.get('reason') for source in inventory['disabledSources']))
        self.assertEqual(sum(len(source['endpoints']) for source in inventory['readySources']), 14)

    def test_missing_policy_blocks_network_for_that_source(self):
        sources = json.loads((ROOT / 'config/sources.yaml').read_text())['sources']
        sources = copy.deepcopy(sources[:1])
        sources[0].pop('policy_evidence')
        with tempfile.TemporaryDirectory() as folder:
            registry = Path(folder) / 'registry.json'
            registry.write_text(json.dumps({'sources': sources}))
            inventory = source_inventory(registry)
            self.assertEqual(inventory['blockedSources'][0]['missingFields'], ['policy_evidence'])
            with patch('services.pipeline.ingest.collect_source') as collect:
                report = probe_archives(registry, fetch=True)
            collect.assert_not_called()
            self.assertFalse(report['articles'])

    def test_offline_gap_report_uses_dated_evidence_without_network_or_store(self):
        with patch('services.pipeline.ingest.collect_source', side_effect=AssertionError('No network')), \
             patch('services.pipeline.ingest.ArticleStore', side_effect=AssertionError('No database')):
            report = probe_archives(ROOT / 'config/sources.yaml')
        self.assertEqual(report['mode'], 'recorded-evidence')
        self.assertEqual(sum(report['recordedDaily'].values()), 55)
        self.assertEqual(report['zeroRecordedDays'], ['2026-11-01'])
        self.assertFalse(report['articles'])
        self.assertTrue(any('not current database' in note for note in report['limitations']))

    def test_unknown_days_are_unknown_rather_than_zero_evidence(self):
        report = probe_archives(ROOT / 'config/sources.yaml', '2026-10-31', '2026-11-01')
        self.assertIsNone(report['recordedDaily']['2026-10-31'])
        self.assertEqual(report['missingRecordedDays'], ['2026-10-31'])

    def test_probe_uses_only_configured_endpoints_keeps_partial_success_and_dates(self):
        article = {'url': 'https://news.mit.edu/test', 'title': 'Original headline',
                   'excerpt': 'Original excerpt', 'publishedAt': '2026-11-01T23:30:00Z',
                   'eventAt': None}
        def collect(source, fixture=False):
            if source['id'] == 'mit-robotics':
                return [dict(article)], [{'status': 200}]
            raise OSError('sensitive transport detail omitted')
        with patch('services.pipeline.ingest.collect_source', side_effect=collect) as call, \
             patch('services.pipeline.ingest.ArticleStore', side_effect=AssertionError('No database')):
            report = probe_archives(ROOT / 'config/sources.yaml', fetch=True)
        self.assertEqual(call.call_count, 14)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['uniqueCanonicalUrls'], 1)
        self.assertEqual(report['observedDaily']['2026-11-01'], 0)
        self.assertEqual(report['observedDaily']['2026-11-02'], 1)
        self.assertIsNone(report['articles'][0]['eventAt'])
        self.assertNotIn('sensitive transport', json.dumps(report))

    def test_unapproved_archive_is_blocked_and_credentials_are_not_reported(self):
        source = copy.deepcopy(json.loads((ROOT / 'config/sources.yaml').read_text())['sources'][0])
        source['archive_feeds'] = ['https://user:secret@private.invalid/feed']
        with tempfile.TemporaryDirectory() as folder:
            registry = Path(folder) / 'registry.json'
            registry.write_text(json.dumps({'sources': [source]}))
            inventory = source_inventory(registry)
        self.assertEqual(len(inventory['blockedSources']), 1)
        self.assertNotIn('secret', json.dumps(inventory))

    def test_duplicate_ids_cannot_substitute_another_source_policy(self):
        source = copy.deepcopy(json.loads((ROOT / 'config/sources.yaml').read_text())['sources'][0])
        duplicate = dict(source, feed_permitted=False)
        with tempfile.TemporaryDirectory() as folder:
            registry = Path(folder) / 'registry.json'
            registry.write_text(json.dumps({'sources': [source, duplicate]}))
            with patch('services.pipeline.ingest.collect_source') as collect:
                report = probe_archives(registry, fetch=True)
        collect.assert_not_called()
        self.assertEqual(len(report['inventory']['blockedSources']), 2)
        self.assertEqual(report['status'], 'blocked')

    def test_event_and_canonical_url_repeats_are_suppressed_without_title_guessing(self):
        articles = [{'url': 'https://news.mit.edu/a?utm_source=x', 'title': 'Same title'},
                    {'url': 'https://news.mit.edu/b', 'eventKey': 'Reviewed-Event', 'title': 'Different title'},
                    {'url': 'https://news.mit.edu/c', 'title': 'Same title'}]
        kept, rejected = suppress_previously_published(articles, ['https://news.mit.edu/a'], ['reviewed-event'])
        self.assertEqual(kept, [articles[2]])
        self.assertEqual([r['reason'] for r in rejected], ['previously_published_url', 'previously_published_event'])

    def test_probe_rejects_unbounded_windows_and_output_outside_artifacts(self):
        with self.assertRaises(ValueError):
            probe_archives(ROOT / 'config/sources.yaml', '2026-11-13', '2026-11-01')
        with self.assertRaises(ValueError):
            probe_archives(ROOT / 'config/sources.yaml', '2026-01-01', '2026-11-01')
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(['--output', 'README.md'])


if __name__ == '__main__':
    unittest.main()
