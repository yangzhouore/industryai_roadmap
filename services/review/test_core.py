"""Synthetic temporary actors only; no actual enrollment, source writes or approvals."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from .analysis import analyze
from .core import Workbench, Session, STORY_CHECKS, EDITION_CHECKS
from .security import ROOT, ReviewError, new_file, private_root

PASSWORD = 'Synthetic-temporary-test-password-only'


def real_shape():
    value = deepcopy(json.loads((ROOT/'packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))[0])
    value['id'] = 'artificial-review-test-only'
    value['synthetic'] = False
    value['stories'] = value['stories'][:1]
    value['sources'] = value['sources'][:1]
    value['sources'][0]['synthetic'] = False
    value['sources'][0]['url'] = 'https://artificial-review-test.invalid/source'
    value['stories'][0]['evidenceStatus'] = 'verified'
    return value


class WorkbenchCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = private_root(Path(self.temporary.name)/'private-state')
        self.evidence_file = new_file(self.root/'synthetic-evidence.txt', b'Artificial test evidence only; not an actual human review or publisher permission.')
        self.evidence = {'reason': {'en': 'Artificial unit-test reason only', 'zh': 'Synthetic bilingual test reason'},
                         'files': [str(self.evidence_file)], 'references': ['https://artificial-review-test.invalid/evidence']}
        self.workbench = Workbench(self.root)
        self.workbench.enroll('test-admin', 'Synthetic Test Administrator', ['administrator', 'reviewer'], PASSWORD, self.evidence, bootstrap=True)
        admin = self.workbench.authenticate('test-admin', PASSWORD)
        self.workbench.enroll('test-author', 'Synthetic Test Author', ['author', 'reviewer'], PASSWORD, self.evidence, session=admin)
        self.workbench.enroll('test-reviewer', 'Synthetic Test Reviewer', ['reviewer'], PASSWORD, self.evidence, session=admin)

    def tearDown(self):
        self.workbench.close()
        self.temporary.cleanup()

    def login(self, name):
        return self.workbench.authenticate(name, PASSWORD)

    def review(self, checks):
        return dict(deepcopy(self.evidence), checks={key: True for key in checks}, riskResolutions=[])

    def test_complete_review_export_revocation_and_history_are_isolated(self):
        source = real_shape()
        before = deepcopy(source)
        revision = self.workbench.import_issue(self.login('test-author'), source, 'Artificial import only')
        changed = deepcopy(source)
        changed['introduction']['en'] = 'Independently drafted artificial test introduction.'
        revised = self.workbench.revise(self.login('test-author'), revision['id'], changed, 'Artificial independent wording revision')
        self.assertEqual(source, before)
        self.assertEqual(self.workbench.candidate(self.login('test-reviewer'), revision['id'])['issue'], before)
        reviewer = self.login('test-reviewer')
        with self.assertRaises(ReviewError):
            self.workbench.bundle(reviewer, revised['id'])
        output = self.workbench.preview(reviewer, revised['id'], self.root/'previews'/'withheld')
        self.assertIn('withheld', (output/'en'/'index.html').read_text(encoding='utf-8').lower())
        with self.assertRaises(ReviewError):
            self.workbench.decide(self.login('test-author'), revised['id'], 'story', changed['stories'][0]['id'], 'approved', self.review(STORY_CHECKS))
        for story in changed['stories']:
            material = self.review(STORY_CHECKS)
            material['claims'] = [{'claim': {'en': 'Artificial test claim', 'zh': 'Synthetic translated test claim'},
                                   'support': {'en': 'Artificial cited evidence', 'zh': 'Synthetic cited evidence'}, 'sourceIds': story['sourceIds']}]
            self.workbench.decide(self.login('test-reviewer'), revised['id'], 'story', story['id'], 'approved', material)
        for source_record in changed['sources']:
            material = dict(deepcopy(self.evidence), url=source_record['url'], publisher=source_record['name'], basis='legal-review', intendedUse='public-web')
            self.workbench.decide(self.login('test-reviewer'), revised['id'], 'link', source_record['id'], 'approved', material)
        final = self.review(EDITION_CHECKS)
        final['riskResolutions'] = [{'findingId': risk['id'], 'reason': {'en': 'Artificial documented resolution only', 'zh': 'Synthetic bilingual resolution only'}} for risk in analyze(changed)]
        self.workbench.finalize(self.login('test-reviewer'), revised['id'], final, PASSWORD)
        bundle = self.workbench.bundle(self.login('test-reviewer'), revised['id'])
        self.assertNotIn('excerpt', bundle['publicIssue']['sources'][0])
        self.assertIn('excerpt', bundle['issue']['sources'][0])
        export = self.workbench.export(self.login('test-reviewer'), revised['id'], self.root/'exports'/'test-bundle.json')
        self.assertTrue(export.is_file())
        with self.assertRaises(ReviewError):
            self.workbench.export(self.login('test-reviewer'), revised['id'], export)
        self.workbench.revoke(self.login('test-reviewer'), revised['id'], self.evidence)
        with self.assertRaises(ReviewError):
            self.workbench.bundle(self.login('test-reviewer'), revised['id'])
        self.assertEqual(len(self.workbench.revisions(self.login('test-author'))), 2)
        self.assertEqual(json.loads((ROOT/'config/public-display.json').read_text())['editions'], [])
        status = self.workbench.status(self.login('test-reviewer'), revised['id'])
        self.assertEqual(len(status['decisions']), 2)
        self.assertEqual(len(status['revocations']), 1)
        audit = self.workbench.audit(self.login('test-reviewer'))
        self.assertNotIn('passwordHash', json.dumps(audit))
        self.assertNotIn('salt', json.dumps(audit))

    def test_auth_roles_lockout_immutable_schema_and_hash_chain(self):
        before = len(self.workbench.verify())
        with patch('services.review.core.pbkdf2_hmac', side_effect=AssertionError('No KDF for invalid password')):
            with self.assertRaises(ReviewError):
                self.workbench.enroll('test-short', 'Synthetic Rejected Account', ['author'], 'x'*14, self.evidence)
        self.assertEqual(len(self.workbench.verify()), before)
        author = self.login('test-author')
        with self.assertRaises(ReviewError):
            self.workbench.import_issue(Session('test-author', 'forged'), real_shape(), 'Artificial import')
        with self.assertRaises(ReviewError):
            self.workbench.import_issue(self.login('test-reviewer'), real_shape(), 'Artificial import')
        for _ in range(5):
            with self.assertRaises(ReviewError):
                self.workbench.authenticate('test-reviewer', 'wrong synthetic password')
        with self.assertRaises(ReviewError):
            self.workbench.authenticate('test-reviewer', PASSWORD)
        revision = self.workbench.import_issue(author, real_shape(), 'Artificial import')
        for query in ('UPDATE events SET actor=actor', 'DELETE FROM events'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.workbench.db.execute(query)
        self.workbench.db.execute('DROP TRIGGER events_no_update')
        with self.assertRaises(ReviewError):
            self.workbench.verify()
        self.assertEqual(revision['issue']['id'], 'artificial-review-test-only')

    def test_editorial_revision_cannot_replace_source_evidence_or_identity(self):
        revision = self.workbench.import_issue(self.login('test-author'), real_shape(), 'Artificial import')
        for mutate in (lambda item: item['sources'][0].update(name='Replaced publisher'),
                       lambda item: item['sources'][0]['excerpt'].update(en='Replaced evidence'),
                       lambda item: item.update(slug='changed-identity'),
                       lambda item: item.update(synthetic=True)):
            proposed = deepcopy(revision['issue'])
            mutate(proposed)
            with self.assertRaises(ReviewError):
                self.workbench.revise(self.login('test-author'), revision['id'], proposed, 'Must be refused')
        proposed = deepcopy(revision['issue'])
        proposed['title']['en'] += ' independently revised'
        revised = self.workbench.revise(self.login('test-author'), revision['id'], proposed, 'Artificial allowed revision')
        self.assertEqual(revised['parentId'], revision['id'])
        with self.assertRaises(ReviewError):
            self.workbench.decide(self.login('test-reviewer'), revision['id'], 'story', proposed['stories'][0]['id'], 'pending', self.review(STORY_CHECKS))


if __name__ == '__main__':
    unittest.main()
