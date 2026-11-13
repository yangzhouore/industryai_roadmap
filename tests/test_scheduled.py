import json
from pathlib import Path
import tempfile
import unittest
from services.pipeline.scheduled import execute


class ScheduledTests(unittest.TestCase):
    def test_success_report(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'status.json'
            result = execute(report_path=report)
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['stats']['issues'], 3)
            self.assertEqual(json.loads(report.read_text()), result)

    def test_failure_is_monitorable(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'status.json'
            result = execute(Path(folder) / 'missing.json', report)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['error'], 'FileNotFoundError')
            self.assertIn('endedAt', json.loads(report.read_text()))
