"""Read-only SQL and interactive-only CLI checks with no real credentials or DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.review.security import ReviewError
from services.review.source import source_editions

ROOT = Path(__file__).resolve().parents[1]


class FakeConnection:
    def __init__(self, readonly='on'):
        self.readonly=readonly; self.calls=[]; self.query=''

    def __enter__(self): return self
    def __exit__(self, *_): pass

    def execute(self, query, parameters=None):
        self.calls.append((query, parameters)); self.query=query; return self

    def fetchone(self): return (self.readonly,)
    def fetchall(self): return [({'id': 'artificial-qa-edition'},)]


class ReviewSourceBoundaryTests(unittest.TestCase):
    def test_source_import_is_readonly_and_identifier_is_parameterized(self):
        connection=FakeConnection()
        connect=unittest.mock.Mock(return_value=connection)
        artificial_id="qa'; DROP TABLE issues; --"
        with patch.dict(sys.modules, {'psycopg': SimpleNamespace(connect=connect)}):
            self.assertEqual(source_editions('artificial-connection', artificial_id), {'id': 'artificial-qa-edition'})
        self.assertIn('default_transaction_read_only=on', connect.call_args.kwargs['options'])
        self.assertEqual(connection.calls[0][0], 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertEqual(connection.calls[1][0], 'SHOW transaction_read_only')
        query, parameters=connection.calls[2]
        self.assertTrue(query.startswith('SELECT '))
        self.assertNotIn(artificial_id, query)
        self.assertEqual(parameters, (artificial_id,))

    def test_nonreadonly_connection_and_driver_errors_fail_without_echo(self):
        secret='postgresql://qa:ARTIFICIAL_PRIVATE_PASSWORD@private.example/db'
        for connect in (unittest.mock.Mock(return_value=FakeConnection('off')),
                        unittest.mock.Mock(side_effect=RuntimeError(secret))):
            with self.subTest(connect=type(connect).__name__), patch.dict(sys.modules, {'psycopg': SimpleNamespace(connect=connect)}):
                with self.assertRaises(ReviewError) as caught:
                    source_editions(secret, 'qa')
                self.assertNotIn('ARTIFICIAL_PRIVATE_PASSWORD', str(caught.exception))
                self.assertNotIn('private.example', str(caught.exception))

    def test_cli_refuses_password_arguments_and_noninteractive_enrollment(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'private-state'
            env=dict(os.environ, PYTHONUTF8='1', REVIEW_PASSWORD='ARTIFICIAL_ENV_PASSWORD')
            for key in list(env):
                if key.startswith('OPENAI_') or key.endswith('DATABASE_URL'): env.pop(key)
            base=[sys.executable,'-m','services.review','--state-dir',str(state)]
            refused=subprocess.run([*base,'--password','ARTIFICIAL_ARGUMENT_PASSWORD','verify'],
                                   input='',text=True,capture_output=True,env=env,timeout=30,cwd=ROOT)
            self.assertNotEqual(refused.returncode,0)
            self.assertNotIn('ARTIFICIAL_ARGUMENT_PASSWORD',refused.stdout+refused.stderr)
            refused=subprocess.run([*base,'enroll','--human-id','qa-test','--name','Artificial QA Actor',
                '--role','administrator','--bootstrap','--identity-evidence',str(Path(folder)/'missing.json')],
                input='ARTIFICIAL_STDIN_PASSWORD\n',text=True,capture_output=True,env=env,timeout=30,cwd=ROOT)
            self.assertEqual(refused.returncode,1)
            self.assertEqual(json.loads(refused.stdout)['status'],'refused')
            self.assertNotIn('ARTIFICIAL_ENV_PASSWORD',refused.stdout+refused.stderr)
            self.assertNotIn('ARTIFICIAL_STDIN_PASSWORD',refused.stdout+refused.stderr)
            self.assertFalse(state.exists(), 'Noninteractive enrollment must not initialize private state')


if __name__ == '__main__':
    unittest.main()
