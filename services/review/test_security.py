"""Fast private filesystem, bridge and CLI regressions; no identities are enrolled."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from . import __main__ as cli
from .security import ROOT, ReviewError, bridge, load_private_json, new_file, private_root
from .source import source_editions


class ReviewBoundaryTests(unittest.TestCase):
    def test_repository_source_and_public_state_paths_refused_before_creation(self):
        for parent in ('docs', 'services', 'apps/web', 'public'):
            target = ROOT/parent/('must-not-create-'+uuid4().hex)
            with self.subTest(parent=parent), self.assertRaises(ReviewError):
                private_root(target)
            self.assertFalse(target.exists())

    def test_private_json_rejects_duplicate_keys_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as folder:
            private = private_root(Path(folder)/'state')
            for index, data in enumerate((b'{"approved":false,"approved":true}', b'{"number":NaN}', b'{"number":Infinity}')):
                path = new_file(private/f'{index}.json', data)
                with self.assertRaises(ReviewError):
                    load_private_json(path)

    def test_shared_bridge_scrubs_paid_database_and_runtime_injection_environment(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-not-real-secret',
                                     'DATABASE_URL': 'postgresql://test:synthetic@localhost/test',
                                     'NODE_OPTIONS': '--require untrusted-file'}), \
             patch('services.review.security.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'{"valid":false}', b'')) as run:
            self.assertEqual(bridge('validate', {}), {'valid': False})
        environment = run.call_args.kwargs['env']
        for key in ('OPENAI_API_KEY', 'DATABASE_URL', 'NODE_OPTIONS'):
            self.assertNotIn(key, environment)
        self.assertNotIn('synthetic', ' '.join(run.call_args.args[0]))

    def test_cli_refuses_no_actor_or_noninteractive_before_creating_state(self):
        with tempfile.TemporaryDirectory() as folder:
            for actor in ([], ['--actor', 'synthetic-user']):
                path = Path(folder)/('unused-'+uuid4().hex)
                output = io.StringIO()
                with redirect_stdout(output), patch.object(cli.sys.stdin, 'isatty', return_value=False):
                    self.assertEqual(cli.main(['--state-dir', str(path), *actor, 'list']), 1)
                self.assertFalse(path.exists())
                self.assertIn('withheld', output.getvalue())

    def test_unknown_password_flags_never_echo_argument_values(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit):
            cli.main(['--password', 'synthetic-sensitive-value'])
        self.assertNotIn('synthetic-sensitive-value', output.getvalue())

    def test_source_errors_never_echo_connection_credentials(self):
        with patch('psycopg.connect', side_effect=RuntimeError('synthetic-private-dsn-value')):
            with self.assertRaises(ReviewError) as raised:
                source_editions('synthetic-private-dsn-value')
        self.assertNotIn('synthetic-private-dsn-value', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
