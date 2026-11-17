"""Production secret filenames must fail scanning even if force-added to Git."""
import unittest
from tests.scan_secrets import forbidden_path


class SecretPathTests(unittest.TestCase):
    def test_service_credentials_and_recovery_material_are_not_source(self):
        for path in ('deploy/linux/environment/web.env', '.env.production.local',
                     'worker.env.production', 'rclone.conf', 'secrets/pgpass',
                     'private/.pgpass', 'private/.pg_service.conf', 'private/credentials-prod.json',
                     'private/service-account-prod.json', 'private/CREDENTIALS.JSON',
                     'private/restore.agekey', 'backup.dump.age', 'artifacts/report.json'):
            with self.subTest(path=path):
                self.assertTrue(forbidden_path(path))

    def test_explicit_blank_examples_and_runtime_code_remain_allowed(self):
        for path in ('.env.example', 'deploy/linux/environment/worker.env.example',
                     'deploy/linux/postgresql/private.conf', 'packages/db/recovery.py'):
            with self.subTest(path=path):
                self.assertFalse(forbidden_path(path))
