"""Daily integration in disposable schemas; all HTTP and source collection is mocked.

The NIST snapshot/date shifts below exercise gates only and never represent a new
publisher announcement. TEST_DATABASE_URL must point to a disposable test database.
"""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from packages.db.automation import AutomationStore
from services.pipeline.daily import cache_get, cache_put, configuration, execute
from services.pipeline.editorial.provider import OpenAIProvider
from services.pipeline.editorial.test_live import ARTICLE, ScriptedHTTP
from services.pipeline.ingest import ArticleStore
from services.pipeline.schedule import run_lock
from services.pipeline.store import Store

ROOT = Path(__file__).resolve().parents[1]
DATABASE = os.getenv('TEST_DATABASE_URL', '')
NOW = datetime(2027, 1, 14, 8, tzinfo=timezone.utc)
DAY = '2027-01-14'


def article():
    return dict(deepcopy(ARTICLE), publishedAt='2027-01-13T12:00:00Z',
                contentHash='fixture-evidence-only')


class UsageHTTP(ScriptedHTTP):
    def __init__(self, mutate=None, fail_stage=None):
        super().__init__(mutate)
        self.fail_stage = fail_stage

    def __call__(self, request):
        stage = request['text']['format']['name'].removeprefix('industrial_')
        if stage == self.fail_stage:
            self.requests.append(deepcopy(request))
            raise TimeoutError('Mock transport interruption')
        response = super().__call__(request)
        response['usage'] = {'input_tokens': 100, 'output_tokens': 100,
                             'output_tokens_details': {'reasoning_tokens': 40}}
        return response


class CachedStageTests(unittest.TestCase):
    def test_sqlite_cache_records_content_without_credentials(self):
        with TemporaryDirectory() as directory:
            auto = AutomationStore(str(Path(directory)/'automation.sqlite'))
            try:
                cache_put(auto, 'stage', {'responseId': 'resp_test', 'data': {'safe': True}})
                self.assertEqual(cache_get(auto, 'stage')['data'], {'safe': True})
                cache_put(auto, 'stage', {'data': {'safe': False}})
                self.assertEqual(cache_get(auto, 'stage')['data'], {'safe': True})
            finally:
                auto.close()


@unittest.skipUnless(DATABASE.startswith(('postgresql://', 'postgres://')),
                     'TEST_DATABASE_URL required; production database is never used')
class DailyAutomationPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.schema = 'daily_test_' + uuid4().hex
        self.admin = psycopg.connect(DATABASE, autocommit=True)
        self.addCleanup(self.cleanup_schema)
        self.admin.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public')
        self.admin.execute('CREATE SCHEMA ' + self.schema)
        parts = urlsplit(DATABASE)
        params = [(k, v) for k, v in parse_qsl(parts.query) if k != 'options']
        params.append(('options', '-c search_path=' + self.schema + ',public'))
        self.location = urlunsplit(parts._replace(query=urlencode(params, quote_via=quote)))
        self.db = psycopg.connect(self.location, autocommit=True)
        for migration in sorted((ROOT/'packages/db/prisma/migrations').glob('*/migration.sql')):
            self.db.execute(migration.read_text(encoding='utf-8'), prepare=False)
        self.config = configuration()
        self.config.update(startDate='2027-01-01', legacyBudgetPath='artifacts/nonexistent-test-ledger.json')
        self.collector = Mock(return_value={'sourcesSucceeded': 1, 'sourcesFailed': 0,
            'articlesSeen': 1, 'articlesInserted': 0, 'errors': [], 'audit': []})
        source = {'id': 'nist', 'name': 'NIST', 'homepage': 'https://www.nist.gov',
                  'feed_url': 'https://www.nist.gov/test-feed', 'synthetic': False}
        raw = ArticleStore(self.location)
        try:
            raw.persist_source(source, [article()])
        finally:
            raw.close()

    def cleanup_schema(self):
        if hasattr(self, 'db'):
            self.db.close()
        self.admin.execute('DROP SCHEMA IF EXISTS ' + self.schema + ' CASCADE')
        self.admin.close()

    def count(self, table, where=''):
        return self.db.execute('SELECT count(*) FROM ' + table + (' WHERE ' + where if where else '')).fetchone()[0]

    def factory(self, transport):
        def build(**kwargs):
            return OpenAIProvider(api_key='unit-test-credential', transport=transport, **kwargs)
        return build

    def run_daily(self, transport=None, **options):
        values = dict(day=DAY, now=NOW, dry_run=False, allow_paid=True,
                      config=self.config, collector=self.collector,
                      provider_factory=self.factory(transport or UsageHTTP()))
        values.update(options)
        return execute(self.location, **values)

    def test_default_dry_run_does_not_collect_call_or_write(self):
        network = Mock(side_effect=AssertionError('Network forbidden'))
        tables = ('issues', 'raw_articles', 'pipeline_runs', 'automation_runs', 'api_requests', 'automation_cache')
        before = {name: self.count(name) for name in tables}
        result = execute(self.location, day=DAY, now=NOW, config=self.config,
                         collector=self.collector, provider_factory=network)
        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['candidatesConsidered'], 1)
        self.assertIn('endedAt', result)
        self.assertEqual(before, {name: self.count(name) for name in tables})
        self.collector.assert_not_called()
        network.assert_not_called()

    def test_paid_and_scheduled_approval_guards_fail_closed(self):
        for options in ({'allow_paid': False}, {'scheduled': True}):
            with self.subTest(options=options):
                network = Mock(side_effect=AssertionError('Provider forbidden'))
                with patch.dict(os.environ, {'UNATTENDED_PAID_APPROVED': 'false'}):
                    result = self.run_daily(provider_factory=network, **options)
                self.assertEqual(result['status'], 'authorization_required')
                self.assertIn('endedAt', result)
                network.assert_not_called()
        self.assertEqual(self.count('api_requests'), 0)
        self.collector.assert_not_called()

    def test_overlap_skips_without_collection_or_paid_requests(self):
        owner = AutomationStore(self.location)
        try:
            with run_lock(owner, self.location):
                result = self.run_daily()
            self.assertEqual(result['status'], 'overlap_skipped')
            self.assertEqual(self.count('api_requests'), 0)
            self.collector.assert_not_called()
        finally:
            owner.close()

    def test_publish_is_bilingual_and_repeated_run_is_idempotent(self):
        transport = UsageHTTP()
        result = self.run_daily(transport)
        self.assertEqual(result['status'], 'published', result)
        self.assertEqual(self.count('issues', "state='published'"), 1)
        self.assertEqual(self.count('translations'), 2)
        self.assertEqual(self.count('automation_events'), 1)
        self.assertEqual(self.count('edition_revisions'), 1)
        archived, review = self.db.execute('SELECT content,review FROM edition_revisions').fetchone()
        self.assertEqual(archived, self.db.execute('SELECT content FROM issues').fetchone()[0])
        from services.pipeline.verification.review import issue_digest
        self.assertEqual(review['issueHash'], issue_digest(archived))
        self.assertEqual(self.count('api_requests', "status='measured' AND stage NOT LIKE 'legacy%'"), 3)
        before = self.count('api_requests')
        repeat = self.run_daily(UsageHTTP())
        self.assertEqual(repeat['status'], 'unchanged')
        self.assertEqual(self.count('api_requests'), before)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(self.collector.call_count, 1)

    def test_partial_collection_failure_is_observable_and_other_source_can_publish(self):
        self.collector.return_value.update(sourcesFailed=1,
            errors=[{'sourceId': 'unavailable', 'error': 'Unavailable feed'}])
        result = self.run_daily()
        self.assertEqual(result['status'], 'published', result)
        self.assertEqual(result['collection']['sourcesFailed'], 1)
        self.assertEqual(result['collection']['errors'][0]['sourceId'], 'unavailable')

    def test_total_collection_failure_never_calls_provider(self):
        self.collector.return_value.update(sourcesSucceeded=0, sourcesFailed=1)
        network = Mock(side_effect=AssertionError('Provider forbidden'))
        result = self.run_daily(provider_factory=network)
        self.assertEqual(result['status'], 'collection_failed')
        self.assertIn('endedAt', result)
        network.assert_not_called()
        self.assertEqual(self.count('issues'), 0)

    def test_review_rejection_keeps_private_draft_and_requires_resume(self):
        def reject(stage, data):
            if stage == 'verify':
                data['claims'][0]['supported'] = False
        result = self.run_daily(UsageHTTP(reject))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['verification'], 'rejected')
        self.assertEqual(self.count('issues', "state='published'"), 0)
        self.assertEqual(self.count('issues', "state='draft' AND validated=false"), 1)
        self.assertEqual(self.count('automation_events'), 0)
        self.assertIn('unsupported', result['reason'])
        repeated = self.run_daily()
        self.assertEqual(repeated['status'], 'resume_required')

    def test_resume_rechecks_rejected_review_without_recharging_accepted_stages(self):
        def reject(stage, data):
            if stage == 'verify':
                data['claims'][0]['supported'] = False
        first = self.run_daily(UsageHTTP(reject))
        self.assertEqual(first['status'], 'failed')
        transport = UsageHTTP()
        resumed = self.run_daily(transport, resume=True)
        self.assertEqual(resumed['status'], 'published', resumed)
        self.assertEqual(resumed['cachedStagesReused'], 2)
        self.assertEqual([r['text']['format']['name'] for r in transport.requests], ['industrial_verify'])
        self.assertEqual(self.count('api_requests', "stage NOT LIKE 'legacy%'"), 4)

    def test_resume_retries_invalid_classification_instead_of_caching_it_forever(self):
        def invalid(stage, data):
            if stage == 'classify':
                data['classifications'][0].pop('maturity')
        first = self.run_daily(UsageHTTP(invalid))
        self.assertEqual(first['status'], 'failed')
        transport = UsageHTTP()
        resumed = self.run_daily(transport, resume=True)
        self.assertEqual(resumed['status'], 'published', resumed)
        self.assertEqual(resumed['cachedStagesReused'], 0)
        self.assertEqual(len(transport.requests), 3)

    def test_budget_exhaustion_stops_before_transport_and_retains_audit(self):
        self.config['monthlyBudgetUSD'] = .000001
        transport = UsageHTTP()
        result = self.run_daily(transport)
        self.assertEqual(result['status'], 'budget_stopped', result)
        self.assertEqual(transport.requests, [])
        self.assertEqual(self.count('issues', "state='published'"), 0)
        self.assertEqual(self.count('automation_events'), 0)
        self.assertEqual(self.count('automation_runs', "status='budget_stopped'"), 1)

    def test_new_url_for_previously_reviewed_event_is_not_published_again(self):
        self.assertEqual(self.run_daily()['status'], 'published')
        second = dict(article(), url=ARTICLE['url']+'?daily-test=new-announcement',
                      publishedAt='2027-01-14T12:00:00Z')
        source = {'id': 'nist', 'name': 'NIST', 'homepage': 'https://www.nist.gov',
                  'feed_url': 'https://www.nist.gov/test-feed', 'synthetic': False}
        raw = ArticleStore(self.location)
        try:
            raw.persist_source(source, [second])
        finally:
            raw.close()
        transport = UsageHTTP()
        result = self.run_daily(transport, day='2027-01-15',
                                now=datetime(2027, 1, 15, 8, tzinfo=timezone.utc))
        self.assertEqual(result['status'], 'no_eligible_news', result)
        self.assertEqual(self.count('issues', "state='published'"), 1)
        self.assertEqual(self.count('automation_events'), 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(result['editorialTrace']['rejections'][0]['reason'], 'previously_published_event')

    def test_incomplete_bilingual_output_never_publishes(self):
        def incomplete(stage, data):
            if stage == 'generate':
                data['stories'][0]['summary']['zh'] = ''
        result = self.run_daily(UsageHTTP(incomplete))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.count('issues', "state='published'"), 0)
        self.assertEqual(self.count('translations'), 0)
        self.assertEqual(self.count('automation_events'), 0)

    def test_resume_reuses_successful_stages_and_retains_unknown_request_reservation(self):
        first = self.run_daily(UsageHTTP(fail_stage='verify'))
        self.assertEqual(first['status'], 'failed')
        unresolved = self.count('api_requests', "status='reserved'")
        self.assertEqual(unresolved, 1)
        collector = Mock(side_effect=AssertionError('Resume must reuse collection snapshot'))
        transport = UsageHTTP()
        resumed = self.run_daily(transport, resume=True, collector=collector)
        self.assertEqual(resumed['status'], 'published', resumed)
        self.assertEqual(resumed['cachedStagesReused'], 2)
        self.assertEqual([r['text']['format']['name'] for r in transport.requests], ['industrial_verify'])
        self.assertEqual(self.count('api_requests', "status='reserved'"), unresolved)
        self.assertEqual(self.count('api_requests', "stage NOT LIKE 'legacy%'"), 4)

    def test_publication_failure_rolls_back_event_claims_and_normalized_rows(self):
        def fail(*args, **kwargs):
            raise RuntimeError('Injected publication failure')
        with patch.object(Store, '_persist_evidence', fail):
            result = self.run_daily()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.count('issues', "state='published'"), 0)
        self.assertEqual(self.count('translations'), 0)
        self.assertEqual(self.count('automation_events'), 0)
        self.assertEqual(self.count('issues', "state='draft'"), 1)
        self.assertEqual(self.count('edition_revisions'), 0)

    def test_existing_publication_is_never_replaced_by_a_new_unverified_draft(self):
        self.assertEqual(self.run_daily()['status'], 'published')
        old = self.db.execute('SELECT content FROM issues').fetchone()[0]
        network = Mock(side_effect=AssertionError('Existing edition must short circuit'))
        result = self.run_daily(provider_factory=network, resume=True)
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(self.db.execute('SELECT content FROM issues').fetchone()[0], old)
        network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
