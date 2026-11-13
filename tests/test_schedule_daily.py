from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from packages.db.automation import AutomationStore
from services.pipeline.reporting import redacted
from services.pipeline.schedule import (AlreadyRunning, latest_due, missed_dates,
                                       next_slot, run_lock, slot)


class ScheduleTests(unittest.TestCase):
    def test_seven_berlin_across_both_dst_transitions(self):
        expected = {'2026-03-28': 6, '2026-03-29': 5,
                    '2026-10-24': 5, '2026-10-25': 6}
        for day, hour in expected.items():
            with self.subTest(day=day):
                self.assertEqual(slot(day).astimezone(timezone.utc).hour, hour)
                just_before = datetime.fromisoformat(day + f'T{hour-1:02}:59:59+00:00')
                self.assertNotEqual(latest_due(just_before), day)
                self.assertEqual(next_slot(just_before).date().isoformat(), day)
                self.assertEqual(next_slot(just_before).hour, hour)
                self.assertEqual(latest_due(slot(day)), day)

    def test_catchup_missing_dates_and_completed_runs(self):
        now = datetime.fromisoformat('2026-11-16T07:00:00+01:00')
        self.assertEqual(missed_dates('2026-11-14', ['2026-11-15'], now),
                         ['2026-11-14', '2026-11-16'])
        self.assertEqual(missed_dates('2026-11-17', now=now), [])
        self.assertEqual(next_slot(now).isoformat(), '2026-11-17T06:00:00+00:00')

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            latest_due(datetime(2026, 11, 14, 7))

    def test_overlap_lock_and_release(self):
        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder)/'state.sqlite')
            first, second = AutomationStore(database), AutomationStore(database)
            try:
                with run_lock(first, database):
                    with self.assertRaises(AlreadyRunning):
                        with run_lock(second, database):
                            self.fail('Overlapping runner entered')
                with run_lock(second, database):
                    pass
                try:
                    with run_lock(first, database):
                        raise RuntimeError('Crash simulation')
                except RuntimeError:
                    pass
                with run_lock(second, database):
                    pass
            finally:
                first.close(); second.close()

    def test_operational_reports_redact_nested_credentials(self):
        from unittest.mock import patch
        key = 'sk-unit-private-value'
        with patch.dict('os.environ', {'OPENAI_API_KEY': key}):
            result = redacted({'authorization': 'Bearer '+key,
                               'errors': [{'message': key+' postgresql://u:password@localhost/db'}]})
        self.assertNotIn(key, str(result))
        self.assertNotIn('password', str(result))
        self.assertNotIn('authorization', result)


if __name__ == '__main__':
    unittest.main()
