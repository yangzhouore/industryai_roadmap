"""Guards for CI-only sandbox fallback and isolated database smoke targets."""
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.smoke_database_web import test_database_url

ROOT = Path(__file__).resolve().parents[1]


class WebSmokeSafetyTests(unittest.TestCase):
    def test_database_setup_refuses_production_and_requires_explicit_isolation(self):
        with patch.dict('os.environ', {'CI': '', 'GITHUB_ACTIONS': ''}):
            for url, isolated in (('postgresql://localhost/digest', True),
                                  ('postgresql://localhost/digest_pipeline_test', False),
                                  ('sqlite:///test', True)):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    test_database_url(url, isolated)
            self.assertEqual(test_database_url('postgresql://localhost/digest_pipeline_test', True).path,
                             '/digest_pipeline_test')

    def test_default_ci_database_allowed_only_on_loopback_disposable_runner(self):
        with patch.dict('os.environ', {'CI': 'true', 'GITHUB_ACTIONS': 'true'}):
            test_database_url('postgresql://localhost/digest', True)
            with self.assertRaises(ValueError):
                test_database_url('postgresql://production.invalid/digest', True)

    def test_connection_parameters_cannot_redirect_disposable_target(self):
        with patch.dict('os.environ', {'CI': 'true', 'GITHUB_ACTIONS': 'true'}):
            for parameter in ('host=production.invalid', 'hostaddr=192.0.2.1',
                              'dbname=production', 'user=production',
                              'password=override', 'service=production',
                              'options=-csearch_path=public', 'schema=public'):
                with self.subTest(parameter=parameter), self.assertRaises(ValueError):
                    test_database_url('postgresql://localhost/digest_test?'+parameter, True)
            with self.assertRaises(ValueError):
                test_database_url('postgresql://localhost/digest_test#override', True)

    def test_sandbox_opt_out_guard_cannot_be_activated_on_local_windows(self):
        import os
        import subprocess
        env = dict(os.environ, CI_CHROMIUM_NO_SANDBOX='1', GITHUB_ACTIONS='false', CI='true')
        result = subprocess.run(['node', str(ROOT/'apps/web/tests/browser-smoke.mjs')],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('restricted to explicit GitHub Linux CI', result.stderr)

    def test_browser_target_must_be_loopback_even_without_fallback(self):
        import os
        import subprocess
        env = dict(os.environ, WEB_URL='https://example.org', CI_CHROMIUM_NO_SANDBOX='0')
        result = subprocess.run(['node', str(ROOT/'apps/web/tests/browser-smoke.mjs')],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('isolated loopback fixture server', result.stderr)


if __name__ == '__main__':
    unittest.main()
