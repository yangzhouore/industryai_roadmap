import copy
import json
from pathlib import Path
import tempfile
import unittest
from services.pipeline.store import Store
from services.pipeline.verification import validate_issue

FIXTURES = Path(__file__).resolve().parents[1] / 'packages/shared/fixtures/issues.json'


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.issues = json.loads(FIXTURES.read_text(encoding='utf-8'))
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.directory.name) / 'test.sqlite'))

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_fixture_bilingual_and_replay(self):
        for issue in self.issues:
            self.assertEqual(validate_issue(issue), [])
            self.assertTrue(self.store.publish(issue))
            self.assertFalse(self.store.publish(issue))
        self.assertEqual(len(self.store.published()), 3)

    def test_missing_citation_cannot_publish(self):
        issue = copy.deepcopy(self.issues[0])
        issue['stories'][0]['sourceIds'] = ['missing']
        with self.assertRaises(ValueError):
            self.store.publish(issue)
        self.assertEqual(self.store.published(), [])

    def test_unsupported_claim_cannot_publish(self):
        issue = copy.deepcopy(self.issues[0])
        issue['stories'][0]['summary']['en'] = 'The plant achieved a 99% productivity gain.'
        with self.assertRaises(ValueError):
            self.store.publish(issue)
        self.assertEqual(self.store.published(), [])

    def test_published_editions_are_immutable(self):
        issue = copy.deepcopy(self.issues[0])
        self.store.publish(issue)
        issue['title']['en'] = 'Changed edition title'
        with self.assertRaises(ValueError):
            self.store.publish(issue)
        self.assertEqual(self.store.published()[0]['title'], self.issues[0]['title'])

    def test_draft_not_public(self):
        issue = self.issues[0]
        with self.store.db:
            self.store.execute('INSERT INTO issues(id,slug,issue_date,state,validated,content) VALUES(?,?,?,?,?,?)',
                               (issue['id'],issue['slug'],issue['date'],'draft',False,json.dumps(issue)))
        self.assertEqual(self.store.published(), [])

    def test_draft_identity_cannot_change(self):
        issue = copy.deepcopy(self.issues[0])
        with self.store.db:
            self.store.execute('INSERT INTO issues(id,slug,issue_date,state,validated,content) VALUES(?,?,?,?,?,?)',
                               (issue['id'],issue['slug'],issue['date'],'draft',False,json.dumps(dict(issue,state='draft',validated=False))))
        issue['slug'] = 'revised-identity'
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.store.publish(issue)
        row = self.store.execute('SELECT slug,state FROM issues WHERE id=?',(issue['id'],)).fetchone()
        self.assertEqual(row, (self.issues[0]['slug'],'draft'))

    def test_invalid_input_run_is_audited(self):
        from services.pipeline.cli import run
        path = Path(self.directory.name)
        (path / 'invalid.json').write_text('{invalid JSON',encoding='utf-8')
        with self.assertRaises(ValueError):
            run(['--input',str(path / 'invalid.json'),'--database',str(path / 'failed.sqlite')])
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(path / 'failed.sqlite')) as db:
            self.assertEqual(db.execute('SELECT status FROM run_logs').fetchone()[0], 'failed')
            self.assertEqual(db.execute('SELECT count(*) FROM issues').fetchone()[0], 0)

    def test_dry_run_does_not_create_database(self):
        from services.pipeline.cli import run
        destination = Path(self.directory.name) / 'dry.sqlite'
        stats = run(['--mode','dry-run','--input',str(FIXTURES),'--database',str(destination)])
        self.assertEqual(stats['issues'], 3)
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
