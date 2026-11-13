"""Offline request-ledger, concurrency and recovery regression checks."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from packages.db.automation import AutomationStore
from services.pipeline.budget import BudgetExceeded
from services.pipeline.monthly_budget import MonthlyBudget


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def context(model='gpt-6.1-terra', attempt=0):
    return {'model': model, 'stage': 'generate', 'attempt': attempt,
            'request': {'max_output_tokens': 6000, 'input': 'private evidence is not persisted'}}


def attempt_reservation(path):
    store = AutomationStore(path)
    try:
        MonthlyBudget(store, now=NOW, limit='.04').before(context())
        return True
    except BudgetExceeded:
        return False
    finally:
        store.close()


class MonthlyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = str(Path(self.folder.name) / 'ledger.sqlite')
        self.store = AutomationStore(self.path)
        self.addCleanup(self.store.close)
        self.budget = MonthlyBudget(self.store, now=NOW)

    def test_processes_cannot_overreserve_one_month(self):
        # Every process uses its own connection; BEGIN IMMEDIATE serializes check+insert.
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
            results = list(pool.map(attempt_reservation, [self.path] * 8))
        self.assertEqual(sum(results), 1)
        self.assertLessEqual(self.budget.summary()['estimatedUSD'], .04)
        self.assertEqual(self.budget.summary()['requests'], 1)

    def test_retry_retains_failed_attempt_and_accounts_success(self):
        self.budget.before(context(attempt=0))
        first = self.budget.summary()['estimatedUSD']
        self.budget.before(context(attempt=1))
        self.budget.after({'requestedModel': 'gpt-6.1-terra', 'responseId': 'resp_retry',
                           'usage': {'input_tokens': 1000, 'output_tokens': 1000}})
        report = self.budget.summary()
        self.assertEqual(report['requests'], 2)
        self.assertEqual(report['reservedRequests'], 1)
        self.assertEqual(report['retryRequests'], 1)
        self.assertAlmostEqual(report['estimatedUSD'], first + .006)
        self.assertAlmostEqual(report['reservedUSD'], first)

    def test_usage_settles_original_month_after_midnight(self):
        current = [datetime(2026, 11, 30, 22, 59, tzinfo=timezone.utc)]
        budget = MonthlyBudget(self.store, now=lambda: current[0])
        budget.before(context('gpt-6-luna'))
        current[0] = datetime(2026, 11, 30, 23, 1, tzinfo=timezone.utc)
        budget.after({'usage': {'input_tokens': 1000, 'output_tokens': 1000}})
        self.assertAlmostEqual(budget.summary('2026-11')['estimatedUSD'], .0006)
        self.assertEqual(budget.summary()['month'], '2026-12')
        self.assertEqual(budget.summary()['estimatedUSD'], 0)

    def test_unknown_usage_and_restart_preserve_reservation(self):
        self.budget.before(context())
        reserved = self.budget.summary()['estimatedUSD']
        self.budget.after({'usage': None})
        other = AutomationStore(self.path)
        try:
            resumed = MonthlyBudget(other, now=NOW, limit='.04')
            self.assertEqual(resumed.summary()['estimatedUSD'], reserved)
            with self.assertRaises(BudgetExceeded):
                resumed.before(context())
        finally:
            other.close()

    def test_cache_pricing_and_reasoning_not_double_charged(self):
        self.budget.before(context())
        self.budget.after({'usage': {'input_tokens': 1000, 'output_tokens': 1000,
            'input_tokens_details': {'cached_tokens': 200, 'cache_write_tokens': 100},
            'output_tokens_details': {'reasoning_tokens': 900}}})
        report = self.budget.summary()
        self.assertAlmostEqual(report['estimatedUSD'], .005835)
        self.assertEqual(report['reasoningTokens'], 900)
        self.assertEqual(report['outputTokens'], 1000)

    def test_malformed_usage_cannot_release_reservation(self):
        cases = [
            {'input_tokens': -1, 'output_tokens': 0},
            {'input_tokens': True, 'output_tokens': 0},
            {'input_tokens': 1, 'output_tokens': 0, 'input_tokens_details': {'cached_tokens': 2}},
            {'input_tokens': 1, 'output_tokens': 1, 'output_tokens_details': {'reasoning_tokens': 2}},
            {'input_tokens': 1, 'output_tokens': 1, 'input_tokens_details': 'wrong'},
            {'input_tokens': 1, 'output_tokens': 1, 'input_tokens_details': []},
            {},
        ]
        for usage in cases:
            self.budget.before(context())
            reserved = self.budget.summary()['estimatedUSD']
            with self.assertRaises(BudgetExceeded):
                self.budget.after({'usage': usage})
            self.assertEqual(self.budget.summary()['estimatedUSD'], reserved)

    def test_mismatched_model_or_stage_cannot_release_reserved_cost(self):
        for bad in ({'model': 'gpt-4.1-mini'}, {'requestedModel': 'unknown'}, {'stage': 'verify'}):
            self.budget.before(context())
            reserved = self.budget.summary()['estimatedUSD']
            with self.assertRaises(BudgetExceeded):
                self.budget.after(dict(bad, usage={'input_tokens': 1, 'output_tokens': 1}))
            self.assertEqual(self.budget.summary()['estimatedUSD'], reserved)

    def test_provider_envelope_overrun_records_cost_and_stops(self):
        self.budget.before(context())
        with self.assertRaises(BudgetExceeded):
            self.budget.after({'usage': {'input_tokens': 1000, 'output_tokens': 9000}})
        self.assertAlmostEqual(self.budget.summary()['estimatedUSD'], .046)

    def test_legacy_import_is_atomic_idempotent_and_limits_new_work(self):
        path = Path(self.folder.name) / 'legacy.json'
        path.write_text(json.dumps({'requests': [
            {'model': 'gpt-6.1-terra', 'stage': 'generate', 'charge': 1.99,
             'reserved': 1.99, 'status': 'reserved'}]}), encoding='utf-8')
        self.budget.import_legacy(path)
        self.budget.import_legacy(path)
        self.budget.import_charge('initial-live-2026-11', '2026-11', '.007022')
        self.assertFalse(self.budget.import_charge('initial-live-2026-11', '2026-11', '.007022'))
        self.assertEqual(self.budget.summary()['requests'], 2)
        with self.assertRaises(BudgetExceeded):
            self.budget.before(context())
        with self.assertRaises(BudgetExceeded):
            self.budget.import_charge('initial-live-2026-11', '2026-11', '.1')

    def test_legacy_malformed_file_imports_no_partial_rows(self):
        path = Path(self.folder.name) / 'legacy.json'
        path.write_text(json.dumps({'requests': [
            {'model': 'gpt-6-luna', 'charge': .1}, {'model': 'unknown', 'charge': .1}]}), encoding='utf-8')
        with self.assertRaises(BudgetExceeded):
            self.budget.import_legacy(path)
        self.assertEqual(self.budget.summary()['requests'], 0)

    def test_legacy_known_usage_is_sanitized_and_metadata_can_fill_old_import(self):
        path = Path(self.folder.name) / 'legacy.json'
        record = {'model': 'gpt-6.1-terra', 'stage': 'generate', 'charge': .006,
                  'reserved': .04, 'status': 'measured'}
        path.write_text(json.dumps({'requests': [record]}), encoding='utf-8')
        self.budget.import_legacy(path)
        self.budget.import_charge('initial-live-2026-11', '2026-11', '.007022')
        self.assertEqual(self.budget.summary()['usageUnknownRequests'], 2)
        money = self.store.execute('SELECT estimated_usd,reserved_usd,status FROM api_requests ORDER BY id').fetchall()
        record.update(attempt=1, responseId='resp_imported', usage={
            'input_tokens': 1000, 'output_tokens': 1000, 'untrusted': 'not-for-ledger',
            'input_tokens_details': {'cached_tokens': 200},
            'output_tokens_details': {'reasoning_tokens': 900}})
        path.write_text(json.dumps({'requests': [record]}), encoding='utf-8')
        self.budget.import_legacy(path)
        self.budget.import_legacy(path)
        self.assertEqual(self.store.execute('SELECT estimated_usd,reserved_usd,status FROM api_requests ORDER BY id').fetchall(), money)
        summary = self.budget.summary()
        self.assertEqual(summary['inputTokens'], 1000)
        self.assertEqual(summary['outputTokens'], 1000)
        self.assertEqual(summary['reasoningTokens'], 900)
        self.assertEqual(summary['usageUnknownRequests'], 1)
        self.assertEqual(summary['retryRequests'], 1)
        usage, response = self.store.execute("SELECT usage,response_id FROM api_requests WHERE id LIKE 'legacy-mvp3-%'").fetchone()
        self.assertEqual(response, 'resp_imported')
        self.assertNotIn('untrusted', json.loads(usage))
        self.assertNotIn(b'not-for-ledger', Path(self.path).read_bytes())

    def test_legacy_float_noise_compares_at_database_currency_precision(self):
        path = Path(self.folder.name) / 'legacy.json'
        record = {'model': 'gpt-6.1-terra', 'stage': 'generate', 'status': 'measured',
                  'charge': .006000000000000001, 'reserved': .04000000000000001}
        path.write_text(json.dumps({'requests': [record]}), encoding='utf-8')
        self.budget.import_legacy(path)
        values = self.store.execute('SELECT estimated_usd,reserved_usd FROM api_requests').fetchone()
        self.assertEqual(tuple(map(Decimal, values)), (Decimal('.006'), Decimal('.04')))
        # Simulate an earlier SQLite import that preserved insignificant float tails.
        self.store.execute('UPDATE api_requests SET estimated_usd=?,reserved_usd=?',
                           (str(record['charge']), str(record['reserved'])))
        before = self.store.execute('SELECT estimated_usd,reserved_usd FROM api_requests').fetchone()
        self.budget.import_legacy(path)
        self.assertEqual(self.store.execute('SELECT estimated_usd,reserved_usd FROM api_requests').fetchone(), before)
        self.budget.import_charge('initial-test', '2026-11', .007022000000000001)
        self.assertFalse(self.budget.import_charge('initial-test', '2026-11', '.007022'))

    def test_no_request_or_credentials_stored_and_run_metadata_roundtrips(self):
        run_id = self.store.start_run('2026-11-13', 'manual')
        budget = MonthlyBudget(self.store, run_id, now=NOW)
        budget.before(context())
        self.store.finish_run(run_id, 'blocked', 'budget', {'reason': 'test'}, 'BudgetExceeded')
        record = self.store.runs()[0]
        self.assertEqual(record['stats'], {'reason': 'test'})
        self.assertEqual(record['status'], 'blocked')
        self.assertIsNotNone(record['ended_at'])
        self.assertNotIn(b'private evidence', Path(self.path).read_bytes())
        self.assertEqual(self.store.execute('SELECT run_id FROM api_requests').fetchone()[0], run_id)

    def test_rejects_unknown_models_and_unbounded_config(self):
        with self.assertRaises(ValueError):
            MonthlyBudget(self.store, limit='2.01')
        with self.assertRaises(BudgetExceeded):
            MonthlyBudget(self.store, limit='NaN')
        with self.assertRaises(BudgetExceeded):
            self.budget.before(context('unknown'))
        with self.assertRaises(ValueError):
            MonthlyBudget(self.store, now=datetime(2026, 11, 13)).summary()
        self.assertEqual(self.budget.summary()['requests'], 0)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL', '').startswith(('postgres://', 'postgresql://')),
                     'TEST_DATABASE_URL required for isolated PostgreSQL ledger integration')
class PostgresMonthlyBudgetTests(unittest.TestCase):
    def test_concurrent_connections_cannot_overreserve_month(self):
        import psycopg
        from psycopg import sql
        from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
        from uuid import uuid4
        schema = 'budget_race_test_' + uuid4().hex
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                parts = urlsplit(os.environ['TEST_DATABASE_URL'])
                query = [(k, v) for k, v in parse_qsl(parts.query) if k != 'options']
                query.append(('options', '-c search_path=' + schema + ',public'))
                location = urlunsplit(parts._replace(query=urlencode(query, quote_via=quote)))
                store = AutomationStore(location)
                try:
                    migration = Path(__file__).resolve().parents[1] / 'packages/db/prisma/migrations/20261114000000_daily_automation/migration.sql'
                    store.db.execute(migration.read_text(), prepare=False)
                    barrier = threading.Barrier(2)

                    def reserve(_):
                        # Each worker creates and owns its independent PostgreSQL connection.
                        concurrent = AutomationStore(location)
                        try:
                            budget = MonthlyBudget(concurrent, now=NOW, limit='.04')
                            total = budget._total

                            def slow_total(month):
                                value = total(month)
                                time.sleep(.1)  # Widen check/insert race inside the protected transaction.
                                return value

                            budget._total = slow_total
                            barrier.wait(timeout=10)
                            budget.before(context())
                            return True
                        except BudgetExceeded:
                            return False
                        finally:
                            concurrent.close()

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(reserve, range(2)))
                    self.assertEqual(sorted(results), [False, True])
                    report = MonthlyBudget(store, now=NOW, limit='.04').summary()
                    self.assertEqual(report['requests'], 1)
                    self.assertLessEqual(report['estimatedUSD'], .04)
                finally:
                    store.close()
            finally:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    def test_migration_reservation_and_constraints_in_isolated_schema(self):
        import psycopg
        from psycopg import sql
        from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
        from uuid import uuid4
        schema = 'budget_test_' + uuid4().hex
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                parts = urlsplit(os.environ['TEST_DATABASE_URL'])
                query = [(k, v) for k, v in parse_qsl(parts.query) if k != 'options']
                query.append(('options', '-c search_path=' + schema + ',public'))
                location = urlunsplit(parts._replace(query=urlencode(query, quote_via=quote)))
                store = AutomationStore(location)
                try:
                    migration = Path(__file__).resolve().parents[1] / 'packages/db/prisma/migrations/20261114000000_daily_automation/migration.sql'
                    store.db.execute(migration.read_text(), prepare=False)
                    budget = MonthlyBudget(store, now=NOW)
                    budget.before(context())
                    budget.after({'usage': {'input_tokens': 1000, 'output_tokens': 1000}})
                    self.assertEqual(Decimal(str(budget.summary()['estimatedUSD'])), Decimal('.006'))
                    with tempfile.TemporaryDirectory() as folder:
                        legacy = Path(folder) / 'legacy.json'
                        legacy.write_text(json.dumps({'requests': [{
                            'model': 'gpt-6.1-terra', 'stage': 'generate', 'status': 'measured',
                            'charge': .006000000000000001, 'reserved': .04000000000000001}]}), encoding='utf-8')
                        budget.import_legacy(legacy)
                        budget.import_legacy(legacy)
                        budget.import_charge('initial-test', '2026-11', .007022000000000001)
                        self.assertFalse(budget.import_charge('initial-test', '2026-11', '.007022'))
                        self.assertEqual(Decimal(str(budget.summary()['estimatedUSD'])), Decimal('.019022'))
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        store.execute("UPDATE api_requests SET estimated_usd=-1")
                finally:
                    store.close()
            finally:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    unittest.main()
