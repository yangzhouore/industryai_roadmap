"""Independent review-workbench adversarial checks; all actors/evidence are artificial."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_review_gate_bridge import real_candidate
from services.review.security import ReviewError

PASSWORD = 'Artificial-QA-passphrase-only-2026!'


class ReviewSecurityTests(unittest.TestCase):
    def setUp(self):
        from services.review.core import Workbench
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        from packages.db.recovery import protect_windows_directory
        protect_windows_directory(self.folder)
        if os.name != 'nt': self.folder.chmod(0o700)
        self.evidence = self.folder/'artificial-evidence.txt'
        self.evidence.write_text('Artificial QA review evidence, not publisher permission.', encoding='utf-8')
        self.evidence.chmod(0o600)
        self.workbench = Workbench(self.folder/'private-state')
        self.addCleanup(self.workbench.db.close)
        self.workbench.enroll('qa-admin', 'Artificial QA administrator', ['administrator', 'reviewer'],
                              PASSWORD, self.review(), bootstrap=True)
        admin = self.workbench.authenticate('qa-admin', PASSWORD)
        self.workbench.enroll('qa-author', 'Artificial QA author', ['author'], PASSWORD,
                              self.review(), session=admin)
        self.workbench.enroll('qa-reviewer', 'Artificial QA reviewer', ['reviewer'], PASSWORD,
                              self.review(), session=admin)

    def review(self):
        return {'reason': {'en': 'Artificial QA evidence judgment.', 'zh': '\u4ec5\u7528\u4e8e\u6d4b\u8bd5\u7684\u8bc1\u636e\u5224\u65ad\u3002'},
                'files': [str(self.evidence)], 'references': ['https://evidence.example/qa/review']}

    def session(self, user='qa-reviewer'):
        return self.workbench.authenticate(user, PASSWORD)

    def revision(self):
        return self.workbench.import_issue(self.session('qa-author'), real_candidate(), self.review()['reason']['en'])

    def story_review(self, revision, story):
        from services.review.analysis import analyze
        review = self.review()
        review['checks'] = dict.fromkeys(('originality_en', 'originality_zh', 'facts', 'citations', 'assets'), True)
        review['claims'] = [{'claim': deepcopy(story['summary']), 'sourceIds': story['sourceIds'],
                             'support': {'en': 'Artificial supporting note.', 'zh': '\u6d4b\u8bd5\u652f\u6301\u8bf4\u660e\u3002'}}]
        review['riskResolutions'] = [{'findingId': finding['id'], 'reason': self.review()['reason']}
                                     for finding in analyze(revision['issue'])]
        return review

    def link_review(self, source):
        return dict(self.review(), url=source['url'], publisher=source['name'],
                    basis='legal-review', intendedUse='public-web')

    def completed_reviews(self):
        revision = self.revision()
        for story in revision['issue']['stories']:
            self.workbench.decide(self.session(), revision['id'], 'story', story['id'], 'approved',
                                  self.story_review(revision, story))
        for source in revision['issue']['sources']:
            self.workbench.decide(self.session(), revision['id'], 'link', source['id'], 'approved',
                                  self.link_review(source))
        return revision

    def final_review(self):
        review = self.review()
        review['checks'] = dict.fromkeys(('title_introduction_en', 'title_introduction_zh',
                                         'facts', 'citations', 'assets'), True)
        return review

    def approved(self):
        revision = self.completed_reviews()
        self.workbench.finalize(self.session(), revision['id'], self.final_review(), PASSWORD)
        return revision

    def test_password_authentication_opaque_sessions_and_durable_lockout(self):
        from services.review.core import Workbench
        revision = self.revision()
        session = self.session()
        with patch('services.review.core.time.monotonic', return_value=10**12), self.assertRaises(ReviewError):
            self.workbench.bundle(session, revision['id'])
        other = Workbench(self.folder/'private-state')
        try:
            with self.assertRaises(ReviewError):
                other.bundle(session, revision['id'])
        finally:
            other.close()
        for attempt in range(5):
            with self.subTest(attempt=attempt), self.assertRaises(ReviewError):
                self.workbench.authenticate('qa-reviewer', 'wrong-artificial-password')
        with self.assertRaises(ReviewError):
            self.workbench.authenticate('qa-reviewer', PASSWORD)
        with self.assertRaises(ReviewError):
            self.workbench.bundle({'user': 'qa-admin'}, revision['id'])
        with self.assertRaises(ReviewError):
            self.workbench.bundle(None, revision['id'])
        self.assertNotIn(PASSWORD, (self.folder/'private-state/journal.sqlite').read_bytes().decode('utf-8', errors='ignore'))
        users = [json.loads(row[0]) for row in self.workbench.db.execute("SELECT payload FROM events WHERE kind='user_enrolled'")]
        self.assertEqual(len({user['salt'] for user in users}), 3)
        self.assertTrue(all(user['iterations'] >= 600000 and len(user['salt']) == 64 and
                            user['algorithm'] == 'pbkdf2-sha256' for user in users))
        reopened = Workbench(self.folder/'private-state')
        try:
            with self.assertRaises(ReviewError): reopened.authenticate('qa-reviewer', PASSWORD)
        finally:
            reopened.close()

    def test_credential_named_files_cannot_be_imported_as_evidence(self):
        revision = self.revision(); story = revision['issue']['stories'][0]
        for name in ('worker.env', '.pg_service.conf', 'credentials.json', 'service-account.json'):
            credential = self.folder/name
            credential.write_text('Artificial QA credential-file marker, no real secret.', encoding='utf-8')
            credential.chmod(0o600)
            review = self.story_review(revision, story); review['files'] = [str(credential)]
            with self.subTest(name=name), self.assertRaises(ReviewError):
                self.workbench.decide(self.session(), revision['id'], 'story', story['id'], 'approved', review)

    def test_enrollment_requires_authority_and_cannot_repeat_bootstrap(self):
        with self.assertRaises(ReviewError):
            self.workbench.enroll('qa-short', 'Artificial short-password actor', ['reviewer'],
                                  'Q'*14, self.review(), session=self.session('qa-admin'))
        for kwargs in ({'bootstrap': True}, {'session': self.session('qa-author')}):
            with self.subTest(kwargs=list(kwargs)), self.assertRaises(ReviewError):
                self.workbench.enroll('qa-forged', 'Artificial forged actor', ['reviewer'],
                                      PASSWORD, self.review(), **kwargs)

    def test_unapproved_export_refuses_and_does_not_create_output(self):
        revision = self.revision(); output = self.folder/'no-approval.json'
        with self.assertRaises(ReviewError):
            self.workbench.export(self.session(), revision['id'], output)
        self.assertFalse(output.exists())
        policy = json.loads((Path(__file__).resolve().parents[1]/'config/public-display.json').read_text())
        self.assertEqual(policy['editions'], [])

    def test_roles_cannot_review_own_contributed_lineage(self):
        admin = self.session('qa-admin')
        self.workbench.enroll('qa-dual', 'Artificial dual role', ['author', 'reviewer'],
                              PASSWORD, self.review(), session=admin)
        actor = self.session('qa-dual')
        revision = self.workbench.import_issue(actor, real_candidate(), self.review()['reason']['en'])
        story = revision['issue']['stories'][0]
        with self.assertRaises(ReviewError):
            self.workbench.decide(actor, revision['id'], 'story', story['id'], 'approved',
                                  self.story_review(revision, story))
        changed = deepcopy(revision['issue']); changed['stories'][0]['summary']['en'] += ' Second author edit.'
        child = self.workbench.revise(self.session('qa-author'), revision['id'], changed, self.review()['reason']['en'])
        with self.assertRaises(ReviewError):
            self.workbench.decide(actor, child['id'], 'story', child['issue']['stories'][0]['id'],
                                  'approved', self.story_review(child, child['issue']['stories'][0]))

    def test_final_approval_requires_fresh_password_confirmation(self):
        revision = self.completed_reviews()
        with self.assertRaises(ReviewError):
            self.workbench.finalize(self.session(), revision['id'], self.final_review(), 'wrong-artificial-password')
        with self.assertRaises(ReviewError):
            self.workbench.bundle(self.session(), revision['id'])
        self.workbench.finalize(self.session(), revision['id'], self.final_review(), PASSWORD)
        self.assertEqual(self.workbench.bundle(self.session(), revision['id'])['issue']['id'], revision['issue']['id'])

    def test_approval_requires_real_files_exact_links_and_all_story_checks(self):
        revision = self.revision(); story = revision['issue']['stories'][0]
        cases = []
        missing = self.story_review(revision, story); missing['files'] = [str(self.folder/'missing.txt')]
        cases.append(('story', story['id'], missing))
        false_check = self.story_review(revision, story); false_check['checks']['originality_zh'] = False
        cases.append(('story', story['id'], false_check))
        no_claims = self.story_review(revision, story); no_claims['claims'] = []
        cases.append(('story', story['id'], no_claims))
        source = revision['issue']['sources'][0]
        forged = self.link_review(source); forged['url'] += '/wrong'
        cases.append(('link', source['id'], forged))
        for scope, target, review in cases:
            with self.subTest(scope=scope, review=review), self.assertRaises(ReviewError):
                self.workbench.decide(self.session(), revision['id'], scope, target, 'approved', review)

    def test_revision_and_revocation_invalidate_prior_approval(self):
        revision = self.approved()
        original = self.workbench.bundle(self.session(), revision['id'])
        self.assertEqual(original['issue'], revision['issue'])
        content = self.evidence.read_bytes()
        retained = self.folder/'private-state/evidence'/(hashlib.sha256(content).hexdigest()+'.evidence')
        retained.write_bytes(content+b' artificial tamper')
        with self.assertRaisesRegex(ReviewError, 'Retained evidence integrity'):
            self.workbench.bundle(self.session(), revision['id'])
        retained.write_bytes(content)
        self.assertEqual(self.workbench.bundle(self.session(), revision['id'])['issue'], revision['issue'])
        self.workbench.revoke(self.session(), revision['id'], self.review())
        with self.assertRaisesRegex(ReviewError, 'revoked'):
            self.workbench.bundle(self.session(), revision['id'])
        changed = deepcopy(revision['issue']); changed['stories'][0]['summary']['en'] += ' Revised artificial wording.'
        revised = self.workbench.revise(self.session('qa-author'), revision['id'], changed, self.review()['reason']['en'])
        with self.assertRaises(ReviewError):
            self.workbench.bundle(self.session(), revised['id'])
        with self.assertRaises(ReviewError):
            self.workbench.bundle(self.session(), revision['id'])

    def test_history_triggers_and_chain_reject_tamper(self):
        self.revision()
        for statement in ('UPDATE events SET payload=payload WHERE seq=1', 'DELETE FROM events WHERE seq=1'):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                self.workbench.db.execute(statement)
        self.workbench.db.rollback()
        triggers = self.workbench.db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        self.assertTrue(triggers)
        self.workbench.db.execute('DROP TRIGGER events_no_update')
        self.workbench.db.commit()
        with self.assertRaises(ReviewError):
            self.workbench.verify()
        self.workbench.db.execute("UPDATE events SET payload='{}' WHERE seq=1")
        from services.review.core import TRIGGERS
        self.workbench.db.execute(TRIGGERS['events_no_update'])
        with self.assertRaisesRegex(ReviewError, 'hash-chain'):
            self.workbench.verify()

    def test_concurrent_revisions_cannot_create_two_current_heads(self):
        from services.review.core import Workbench
        parent = self.revision()

        def attempt(number):
            with Workbench(self.folder/'private-state') as workbench:
                actor = workbench.authenticate('qa-author', PASSWORD)
                changed = deepcopy(parent['issue'])
                changed['introduction']['en'] += ' Artificial concurrent edit '+str(number)
                try:
                    workbench.revise(actor, parent['id'], changed, 'Artificial concurrent revision')
                    return 'accepted'
                except ReviewError as error:
                    self.assertIn('stale', str(error))
                    return 'refused'

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sorted(results), ['accepted', 'refused'])
        self.assertEqual(len(self.workbench.revisions(self.session('qa-author'))), 2)


if __name__ == '__main__':
    unittest.main()
