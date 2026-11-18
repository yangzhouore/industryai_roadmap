"""Independent data-only transport and exact public-clearance boundary checks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT/'packages/shared/public-display-cli.cjs'


def bridge(request):
    result = subprocess.run(['node', str(BRIDGE)], input=json.dumps(request),
                            text=True, capture_output=True, timeout=20, cwd=ROOT)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def real_candidate():
    issue = json.loads((ROOT/'packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))[0]
    issue['synthetic'] = False
    for source in issue['sources']:
        source['synthetic'] = False
        source['name'] = 'Artificial QA publisher'
        source['url'] = 'https://publisher.example/qa/'+source['id']
        source['excerpt'] = {'en': 'PRIVATE_EN_EVIDENCE', 'zh': 'PRIVATE_ZH_EVIDENCE'}
    for story in issue['stories']:
        story['evidenceStatus'] = 'verified'
    issue['privateEvidence'] = 'PRIVATE_UNKNOWN_ISSUE'
    issue['stories'][0]['privateEvidence'] = 'PRIVATE_UNKNOWN_STORY'
    return issue


def approval(issue):
    return {'version': 1, 'intendedUse': 'public-web', 'editions': [{
        'issueId': issue['id'], 'contentSha256': bridge({'action': 'hash', 'issue': issue})['hash'],
        'editorialApproved': True, 'reviewedBy': 'Artificial QA reviewer',
        'reviewedAt': '2020-01-01', 'reviewEvidence': 'https://evidence.example/qa/review',
        'sourceLinks': [{'sourceId': source['id'], 'publisher': source['name'],
                         'url': source['url'], 'approved': True, 'basis': 'legal-review',
                         'reviewedBy': 'Artificial QA reviewer', 'reviewedAt': '2020-01-01',
                         'evidenceUrl': 'https://evidence.example/qa/link'} for source in issue['sources']]}]}


class ReviewBridgeTests(unittest.TestCase):
    def test_hash_is_canonical_unicode_json_and_independent_of_key_order(self):
        value = {'z': [1, True, None], 'a': {'zh': '\u539f\u521b', 'en': 'original'}}
        expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                            ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(bridge({'action': 'hash', 'issue': value}), {'hash': expected})
        self.assertEqual(bridge({'action': 'hash', 'issue': dict(reversed(list(value.items())))}), {'hash': expected})

    def test_validation_does_not_grant_clearance_and_fixture_cannot_bypass_bridge(self):
        issue = real_candidate()
        self.assertEqual(bridge({'action': 'validate', 'issue': issue}), {'valid': True})
        for policy in (None, {}, {'version': 1, 'intendedUse': 'public-web', 'editions': []}):
            self.assertEqual(bridge({'action': 'project', 'issue': issue, 'policy': policy}), {'issue': None})
        fixture = json.loads((ROOT/'packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(bridge({'action': 'project', 'issue': fixture, 'fixtureMode': True}), {'issue': None})

    def test_exact_approval_projects_only_allowlisted_fields(self):
        issue = real_candidate()
        projected = bridge({'action': 'project', 'issue': issue, 'policy': approval(issue)})['issue']
        self.assertIsNotNone(projected)
        encoded = json.dumps(projected)
        for private in ('PRIVATE_EN_EVIDENCE', 'PRIVATE_ZH_EVIDENCE', 'PRIVATE_UNKNOWN_ISSUE',
                        'PRIVATE_UNKNOWN_STORY', 'excerpt', 'privateEvidence'):
            self.assertNotIn(private, encoded)
        self.assertEqual(projected['stories'][0]['summary'], issue['stories'][0]['summary'])
        self.assertEqual(projected['sources'][0]['url'], issue['sources'][0]['url'])

    def test_changed_private_evidence_or_editorial_invalidates_exact_approval(self):
        issue = real_candidate(); policy = approval(issue)
        for field in ('evidence', 'editorial', 'source'):
            altered = deepcopy(issue)
            if field == 'evidence': altered['sources'][0]['excerpt']['zh'] += ' edited'
            if field == 'editorial': altered['stories'][0]['summary']['en'] += ' edited'
            if field == 'source': altered['sources'][0]['url'] += '?changed=1'
            with self.subTest(field=field):
                self.assertEqual(bridge({'action': 'project', 'issue': altered, 'policy': policy}), {'issue': None})

    def test_malformed_actions_and_oversized_requests_reject_without_echo(self):
        for data in ('{"action":"execute","issue":"PRIVATE_PAYLOAD"}',
                     'not-json PRIVATE_PAYLOAD', '["PRIVATE_PAYLOAD"]',
                     '{"action":"hash","issue":"'+('X'*(8*1024*1024))+'"}'):
            result = subprocess.run(['node', str(BRIDGE)], input=data, text=True,
                                    capture_output=True, timeout=20, cwd=ROOT)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr.strip(), 'Public-display request rejected.')


if __name__ == '__main__':
    unittest.main()
