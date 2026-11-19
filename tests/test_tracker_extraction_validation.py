"""Synthetic regressions for deterministic extraction response validation."""

from copy import deepcopy
import unittest

from services.tracker.extraction_validation import lifecycle_evidence, validate_candidates
from services.tracker.manifest import TrackerError


PRODUCTION = 'Siemens deployed Orion Cell with a Digital Twin in production.'
STARTED_PILOT = 'Siemens started a pilot for Orion Cell using a Digital Twin.'


def article(article_id='test-article', passage=PRODUCTION, **overrides):
    return {
        'id': article_id, 'sourceId': 'fictional-publisher', 'publisher': 'Fictional newsroom',
        'url': f'https://evidence.test/{article_id}', 'title': 'Siemens fictional case',
        'excerpt': passage, 'publishedAt': '2025-09-08T10:00:00+00:00',
        'eventAt': None, 'sourceTimezone': 'UTC', 'contentHash': 'f' * 64, **overrides,
    }


def fixture(*articles):
    return {'version': 1, 'articles': list(articles) or [article()], 'editions': []}


def proposal(quote=PRODUCTION, article_id='test-article', **overrides):
    return {
        'projectName': 'Orion Cell', 'companyIds': ['siemens'], 'technologyIds': ['digital-twins'],
        'kind': 'deployment', 'stage': 'deployed', 'evidence': [{'articleId': article_id, 'quote': quote}],
        **overrides,
    }


def validate(*proposals, snapshot=None, scope=None):
    return validate_candidates(snapshot or fixture(), {'candidates': list(proposals)}, scope)


class TrackerExtractionValidationTests(unittest.TestCase):
    def test_proposal_retains_exact_evidence_and_pending_status(self):
        row = validate(proposal())['candidates'][0]
        self.assertEqual(row['reviewStatus'], 'pending')
        self.assertEqual((row['kind'], row['stage']), ('deployment', 'deployed'))
        self.assertEqual(row['projectName'], 'Orion Cell')
        self.assertEqual(row['evidence'][0]['quote'], PRODUCTION)
        self.assertEqual(row['evidence'][0]['url'], article()['url'])
        self.assertEqual(row['evidence'][0]['publishedAt'], article()['publishedAt'])
        self.assertIsNone(row['evidence'][0]['eventAt'])
        self.assertNotIn('claim', row)
        self.assertNotIn('expectedRevision', row)

    def test_event_time_is_preserved_only_from_canonical_source(self):
        stamp = '2025-09-02T19:00:00-04:00'
        supplied = fixture(article(eventAt=stamp, sourceTimezone='America/New_York'))
        evidence = validate(proposal(), snapshot=supplied)['candidates'][0]['evidence'][0]
        self.assertEqual(evidence['eventAt'], stamp)
        self.assertEqual(evidence['sourceTimezone'], 'America/New_York')
        self.assertNotEqual(evidence['eventAt'], evidence['publishedAt'])

    def test_invalid_fields_citations_entities_and_names_are_rejected(self):
        malformed = [
            proposal(eventAt='2025-09-01'), proposal(metric=12), proposal(reviewStatus='approved'),
            proposal(projectName='Invented Cell'), proposal(projectName='Siemens'),
            proposal(projectName='rion Cell'), proposal(quote='A fabricated exact quote'),
            proposal(article_id='other-id'), proposal(technologyIds=['predictive-maintenance']),
            proposal(companyIds=['abb']), proposal(companyIds=['made-up-company']), proposal(kind=[]),
            proposal(evidence=[]),
            proposal(evidence=[{'articleId': 'test-article', 'quote': PRODUCTION, 'url': 'https://madeup.test'}]),
        ]
        result = validate(*malformed)
        self.assertEqual(result['rejected'], len(malformed))
        self.assertEqual(result['candidates'], [])

    def test_invalid_scope_and_ambiguous_canonical_snapshot_are_rejected(self):
        snapshots = [fixture(article(), article()), fixture(article(), article('test-other', url=article()['url'])),
                     fixture(article(publishedAt=None)), fixture(article(eventAt='2025-09-01'))]
        for snapshot in snapshots:
            with self.subTest(snapshot=snapshot), self.assertRaises(TrackerError):
                validate(proposal(), snapshot=snapshot)
        self.assertEqual(validate(proposal(), snapshot=fixture(article(), article('test-other')),
                                  scope=['test-other'])['rejected'], 1)
        with self.assertRaisesRegex(TrackerError, 'scope'):
            validate(proposal(), scope=['unknown'])

    def test_external_response_cannot_mix_assigned_article_ids(self):
        snapshot = fixture(article(), article('test-other'))
        out = validate(proposal(article_id='test-other'), snapshot=snapshot, scope=['test-article'])
        self.assertEqual(out['candidates'], [])
        self.assertEqual(out['rejected'], 1)

    def test_aliases_resolve_and_publisher_names_are_provenance_only(self):
        result = validate(proposal(companyIds=[' Siemens AG ', '西门子'],
                                   technologyIds=['DIGITAL TWIN', '数字孪生']))
        row = result['candidates'][0]
        self.assertEqual(row['companyIds'], ['siemens'])
        self.assertEqual(row['technologyIds'], ['digital-twins'])
        publisher_only = fixture(article(passage='Orion Cell deployed a Digital Twin in production.',
                                         title='Fictional case', publisher='Siemens'))
        self.assertEqual(validate(proposal(quote=publisher_only['articles'][0]['excerpt']),
                                  snapshot=publisher_only)['rejected'], 1)

    def test_future_negated_and_pilot_only_deployments_are_downgraded(self):
        for passage, quote in (
            ('Siemens has not deployed Orion Cell with a Digital Twin in production.',
             'deployed Orion Cell with a Digital Twin in production.'),
            ('Siemens will begin with Orion Cell deployed in production using a Digital Twin.',
             'Orion Cell deployed in production using a Digital Twin.'),
            ('Siemens deployed Orion Cell in a Digital Twin pilot.',
             'deployed Orion Cell in a Digital Twin pilot.'),
            ('Siemens announced a Digital Twin deployment for Orion Cell.',
             'announced a Digital Twin deployment for Orion Cell.'),
            ('Siemens deployed Orion Cell with a Digital Twin to a staging environment.',
             'deployed Orion Cell with a Digital Twin to a staging environment.'),
        ):
            with self.subTest(passage=passage):
                result = validate(proposal(quote=quote), snapshot=fixture(article(passage=passage)))
                row = result['candidates'][0]
                self.assertEqual((row['kind'], row['stage']), ('unresolved', None))
                self.assertEqual(row['evidence'][0]['quote'], quote)

    def test_cues_cannot_attach_to_another_project_or_an_uncited_clause(self):
        for connector in (', while ', ' and '):
            passage = 'Orion Cell hired staff' + connector + 'Cedar Cell went live with a Digital Twin.'
            data = fixture(article(passage=passage))
            for quote in ('Orion Cell hired staff', passage):
                with self.subTest(quote=quote):
                    row = validate(proposal(quote=quote), snapshot=data)['candidates'][0]
                    self.assertEqual((row['kind'], row['stage']), ('unresolved', None))
            result = validate(proposal(quote='Cedar Cell went live with a Digital Twin.'), snapshot=data)
            self.assertEqual(result['rejected'], 1)

    def test_dates_and_metrics_cannot_serve_as_project_names(self):
        data = fixture(article(passage='A Digital Twin went live with 80% accuracy on 2025-09-01.'))
        for name in ('80% accuracy', '2025-09-01'):
            with self.subTest(name=name):
                result = validate(proposal(quote=data['articles'][0]['excerpt'], projectName=name), snapshot=data)
                self.assertEqual(result['rejected'], 1)

    def test_unstarted_milestones_and_company_names_do_not_establish_maturity(self):
        cases = (
            ('Siemens announced a pilot program for Orion Cell with a Digital Twin.', 'pilot', 'pilot'),
            ('The Siemens Research Institute opened a sales desk for Orion Cell with a Digital Twin.', 'research', 'research'),
            ('Siemens issued specifications for a future prototype of Orion Cell with a Digital Twin.', 'prototype', 'prototype'),
        )
        for passage, kind, stage in cases:
            with self.subTest(kind=kind):
                result = validate(proposal(quote=passage, kind=kind, stage=stage),
                                  snapshot=fixture(article(passage=passage)))
                row = result['candidates'][0]
                self.assertEqual((row['kind'], row['stage']), ('unresolved', None))

    def test_precisely_stated_announcement_pilot_scale_and_research_stay_distinct(self):
        examples = [
            ('Siemens announced plans for Orion Cell using a Digital Twin.', 'announcement', None),
            (STARTED_PILOT, 'pilot', 'pilot'),
            ('Siemens scaled Orion Cell across other sites using a Digital Twin.', 'scaling', 'scaling'),
            ('Siemens researchers trained Orion Cell in simulation with a Digital Twin.', 'research', 'research'),
        ]
        for passage, kind, stage in examples:
            with self.subTest(kind=kind):
                result = validate(proposal(quote=passage, kind=kind, stage=stage),
                                  snapshot=fixture(article(passage=passage)))
                row = result['candidates'][0]
                self.assertEqual((row['kind'], row['stage']), (kind, stage))
        self.assertFalse(lifecycle_evidence('deployment', 'Deployment guides describe taking steps.'))

    def test_multi_source_conflict_downgrades_lifecycle(self):
        second = 'Siemens has never deployed Orion Cell with a Digital Twin in production.'
        data = fixture(article(), article('test-other', second))
        result = validate(proposal(evidence=[
            {'articleId': 'test-article', 'quote': PRODUCTION},
            {'articleId': 'test-other', 'quote': second},
        ]), snapshot=data)
        row = result['candidates'][0]
        self.assertEqual((row['kind'], row['stage']), ('unresolved', None))
        self.assertEqual(len(row['evidence']), 2)

    def test_duplicate_evidence_sets_coalesce_independently_of_order(self):
        data = fixture(article(passage=PRODUCTION + ' ' + STARTED_PILOT))
        deployment = proposal()
        pilot = proposal(quote=STARTED_PILOT, kind='pilot', stage='pilot', projectName=None, technologyIds=[])
        first = validate(deployment, pilot, snapshot=data)
        self.assertEqual(first, validate(pilot, deployment, snapshot=deepcopy(data)))
        self.assertEqual(first['duplicates'], 1)
        self.assertEqual(first['rejected'], 0)
        row = first['candidates'][0]
        self.assertEqual((row['kind'], row['stage']), ('unresolved', None))
        self.assertIsNone(row['projectName'])
        self.assertEqual(row['technologyIds'], [])


if __name__ == '__main__':
    unittest.main()
