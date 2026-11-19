"""Synthetic regression cases for private tracker curation, without database access."""

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.review.security import ReviewError, read_private
from services.tracker import evidence_snapshot
from services.tracker.inventory import inventory
from services.tracker.manifest import Catalog, TrackerError, parse_change
from services.tracker.store import issue_bridge


PUBLICATION_TIME = '2025-01-02T08:00:00+00:00'
RETAINED_QUOTE = 'The test pilot started in a fictional facility.'


def article(article_id='fixture-article', **overrides):
    return {
        'id': article_id,
        'sourceId': 'fixture-publisher',
        'publisher': 'Fictional vendor',
        'url': f'https://publisher.test/{article_id}',
        'title': 'Siemens fixture coverage',
        'excerpt': RETAINED_QUOTE,
        'publishedAt': PUBLICATION_TIME,
        'eventAt': None,
        'sourceTimezone': 'UTC',
        'contentHash': 'a' * 64,
        **overrides,
    }


def issue(raw, issue_id='fixture-edition'):
    text = {'en': 'Fictional test content', 'zh': '虚构测试内容'}
    return {
        'id': issue_id,
        'slug': issue_id,
        'date': '2025-01-02',
        'state': 'published',
        'validated': True,
        'synthetic': False,
        'title': text,
        'introduction': text,
        'sources': [{
            'id': 'fixture-story-source',
            'synthetic': False,
            'url': raw['url'],
            'name': raw['publisher'],
            'publishedAt': raw['publishedAt'],
            'eventAt': raw['eventAt'],
            'timezone': raw['sourceTimezone'],
            'excerpt': text,
        }],
        'stories': [{
            'id': 'fixture-story',
            'company': 'Siemens',
            'category': 'Digital Twins',
            'maturity': 'pilot',
            'kind': 'feature',
            'evidenceStatus': 'verified',
            'score': 50,
            'sourceIds': ['fixture-story-source'],
            'title': text,
            'summary': text,
            'why': text,
            'limitation': text,
        }],
    }


def evidence_snapshot_fixture():
    raw = article()
    content = issue(raw)
    story = content['stories'][0]
    return {
        'version': 1,
        'articles': [raw],
        'editions': [{
            'id': content['id'],
            'slug': content['slug'],
            'content': content,
            'bindings': [{
                'storyId': story['id'],
                'rawArticleId': raw['id'],
                'claimKey': 'fixture-claim',
                'sourceUrl': raw['url'],
            }],
        }],
    }


def candidate(**overrides):
    return {
        'projectKey': 'fixture-project',
        'milestoneKey': 'fixture-pilot',
        'name': 'Fictional project',
        'claim': 'The fictional source reports the start of a test pilot.',
        'classification': 'pilot',
        'stage': 'pilot',
        'companies': [{'id': 'siemens', 'role': 'vendor'}],
        'technologies': ['digital-twins'],
        'evidence': [{'articleId': 'fixture-article', 'kind': 'vendor', 'quote': RETAINED_QUOTE}],
        'status': 'supported',
        'reason': 'The artificial source explicitly reports the test pilot.',
        'binding': {'issueId': 'fixture-edition', 'storyId': 'fixture-story'},
        **overrides,
    }


def curate(snapshot, *candidates):
    from services.tracker.evidence_batch import prepare

    return prepare(snapshot, {'version': 1, 'candidates': list(candidates)})


class TrackerEvidenceInventoryTests(unittest.TestCase):
    def test_index_is_order_independent_and_keeps_mentions_distinct_from_publisher(self):
        snapshot = evidence_snapshot_fixture()
        articles = snapshot['articles'] + [
            article('acronym', title='AWS and ＡＢＢ', excerpt='Amazon Web Services', publisher='Other'),
            article('false-positive', title='DRAWSTRING and ABBYY', excerpt='aws, Amazon, and Azure', publisher='Other'),
            article('publisher-only', title='Unrelated fixture', excerpt='No attribution in the prose', publisher='NVIDIA'),
        ]
        indexed = inventory(articles, snapshot['editions'])
        self.assertEqual(indexed, inventory(list(reversed(articles)), snapshot['editions']))
        companies = indexed['companies']
        self.assertEqual([row['id'] for row in companies['aws']['articles']], ['acronym'])
        self.assertEqual([row['id'] for row in companies['abb']['articles']], ['acronym'])
        self.assertEqual(companies['microsoft']['counts']['articles'], 0)
        self.assertEqual(companies['nvidia']['counts']['publisher'], 1)
        self.assertEqual(companies['nvidia']['counts']['title'], 0)
        self.assertEqual(companies['nvidia']['counts']['excerpt'], 0)
        siemens_reference = companies['siemens']['articles'][0]
        self.assertEqual(siemens_reference['publishedAt'], PUBLICATION_TIME)
        self.assertIsNone(siemens_reference['eventAt'])
        self.assertEqual(siemens_reference['editionLinks'][0]['sourceUrl'], articles[0]['url'])
        self.assertNotIn(RETAINED_QUOTE, json.dumps(indexed))

    def test_inventory_citation_requires_story_and_exact_canonical_url(self):
        for mutation in ({'sourceUrl': 'https://publisher.test/different'}, {'storyId': 'missing'}):
            with self.subTest(mutation=mutation):
                snapshot = evidence_snapshot_fixture()
                snapshot['editions'][0]['bindings'][0].update(mutation)
                company = inventory(snapshot['articles'], snapshot['editions'])['companies']['siemens']
                self.assertEqual(company['counts']['editionBoundArticles'], 0)
                self.assertEqual(company['counts']['classifiedStories'], 1)


class TrackerEvidenceOutputTests(unittest.TestCase):
    def test_output_path_is_confined_and_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(evidence_snapshot, 'ROOT', root):
                for outside in (root / 'exposed.json', root / 'artifacts' / '..' / 'outside.json'):
                    with self.subTest(outside=outside), self.assertRaises(TrackerError):
                        evidence_snapshot.private_output(outside)
                output = evidence_snapshot.private_output(root / 'artifacts' / 'private' / 'batch.json')
                evidence_snapshot.write_json(output, {'version': 1})
                original = read_private(output)
                with self.assertRaises(ReviewError):
                    evidence_snapshot.write_json(output, {'version': 2})
                self.assertEqual(read_private(output), original)

    @unittest.skipIf(os.name == 'nt', 'POSIX mode checks do not describe Windows ACLs')
    def test_new_private_output_has_no_group_or_other_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(evidence_snapshot, 'ROOT', root):
                output = evidence_snapshot.private_output(root / 'artifacts' / 'private' / 'inventory.json')
                evidence_snapshot.write_json(output, {'version': 1})
                self.assertEqual(stat.S_IMODE(output.parent.stat().st_mode) & 0o077, 0)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode) & 0o077, 0)


class TrackerEvidenceSnapshotTests(unittest.TestCase):
    def test_snapshot_aborts_before_reading_records_when_session_is_writable(self):
        with patch('psycopg.connect') as connect:
            db = connect.return_value.__enter__.return_value
            state = MagicMock()
            state.fetchone.return_value = {'transaction_read_only': 'off'}
            db.execute.side_effect = [None, state]
            with self.assertRaises(TrackerError):
                evidence_snapshot.snapshot('postgresql://unused.test/fictional')
            self.assertIn('default_transaction_read_only=on', connect.call_args.kwargs['options'])
            self.assertEqual(db.execute.call_count, 2)
            self.assertIn('REPEATABLE READ READ ONLY', db.execute.call_args_list[0].args[0])


class TrackerEvidenceBatchTests(unittest.TestCase):
    def test_manifest_uses_shared_edition_hash_and_original_story_source_id(self):
        snapshot = evidence_snapshot_fixture()
        record = candidate()
        result = curate(snapshot, record)
        changes = result['manifest']['changes']
        self.assertEqual(len(changes), 1)
        change = changes[0]
        expected_hash = issue_bridge('hash', snapshot['editions'][0]['content'])['hash']
        self.assertEqual(change['issueHash'], expected_hash)
        self.assertEqual(change['sourceRoles'], {'fixture-story-source': 'vendor'})
        self.assertEqual(change['expectedRevision'], 0)
        self.assertEqual(parse_change(change, Catalog.load()).story_id, record['binding']['storyId'])
        self.assertNotIn(RETAINED_QUOTE, json.dumps(result['manifest']))
        self.assertIn(RETAINED_QUOTE, json.dumps(result['dataset']))
        reference = result['dataset']['candidates'][0]['references'][0]
        self.assertEqual(reference['id'], 'fixture-article')
        self.assertEqual(reference['publishedAt'], PUBLICATION_TIME)
        self.assertIsNone(reference['eventAt'])

    def test_explicit_unresolved_and_raw_only_candidates_remain_private(self):
        snapshot = evidence_snapshot_fixture()
        unbound = candidate()
        del unbound['binding']
        deferred = candidate(
            milestoneKey='possible-production',
            status='unresolved',
            stage=None,
            classification='unresolved',
            reason='No evidence of production use.',
        )
        result = curate(snapshot, unbound, deferred)
        self.assertEqual(result['manifest']['changes'], [])
        self.assertEqual(len(result['dataset']['candidates']), 2)
        self.assertEqual({row['status'] for row in result['dataset']['candidates']}, {'supported', 'unresolved'})
        coverage = result['coverage']
        self.assertEqual(coverage['supportedProjects'], 1)
        self.assertEqual(coverage['supportedMilestones'], 1)
        self.assertEqual(coverage['unresolved'], 1)
        self.assertEqual(coverage['importEligibleMilestones'], 0)
        self.assertEqual(coverage['independentlyVerifiedMilestones'], 0)
        self.assertEqual(coverage['byCompany']['siemens']['supportedMilestones'], 1)

    def test_unmatched_quote_and_unknown_reference_are_rejected(self):
        invalid_evidence = [
            {'articleId': 'fixture-article', 'kind': 'vendor', 'quote': RETAINED_QUOTE.lower()},
            {'articleId': 'missing', 'kind': 'vendor', 'quote': RETAINED_QUOTE},
        ]
        for evidence in invalid_evidence:
            with self.subTest(evidence=evidence), self.assertRaises(TrackerError):
                curate(evidence_snapshot_fixture(), candidate(evidence=[evidence]))

    def test_announcement_and_unapproved_independence_do_not_become_facts(self):
        snapshot = evidence_snapshot_fixture()
        for candidate_row in (
            candidate(classification='announcement', stage='deployed'),
            candidate(evidence=[{'articleId': 'fixture-article', 'kind': 'independent', 'quote': RETAINED_QUOTE}]),
        ):
            with self.subTest(candidate_row=candidate_row), self.assertRaises(TrackerError):
                curate(snapshot, candidate_row)

    def test_wrong_original_attribution_and_unsuitable_stage_block_import(self):
        original = evidence_snapshot_fixture()
        for field, value in (
            ('name', 'Other publisher'),
            ('url', 'https://publisher.test/mismatched-path'),
            ('publishedAt', '2025-01-02T10:00:00+00:00'),
            ('eventAt', '2025-01-02T10:00:00+00:00'),
            ('timezone', 'Europe/London'),
        ):
            with self.subTest(field=field):
                snapshot = deepcopy(original)
                snapshot['editions'][0]['content']['sources'][0][field] = value
                self.assertEqual(curate(snapshot, candidate())['manifest']['changes'], [])
        wrong_stage = candidate(classification='deployment', stage='deployed')
        conflict = curate(original, wrong_stage)
        self.assertEqual(conflict['manifest']['changes'], [])
        self.assertEqual(conflict['dataset']['candidates'][0]['status'], 'unresolved')
        self.assertEqual(conflict['dataset']['candidates'][0]['proposedStage'], 'deployed')
        self.assertIsNone(conflict['dataset']['candidates'][0]['stage'])
        self.assertEqual(conflict['coverage']['supportedMilestones'], 0)

    def test_compiler_rejects_unrelated_company_and_preserves_correction_head(self):
        snapshot = evidence_snapshot_fixture()
        with self.assertRaisesRegex(TrackerError, 'must appear'):
            curate(snapshot, candidate(companies=[{'id': 'nvidia', 'role': 'provider'}]))
        corrected = curate(snapshot, candidate(expectedRevision=2))
        self.assertEqual(corrected['manifest']['changes'][0]['expectedRevision'], 2)

    def test_unvalidated_edition_cannot_issue_an_import_change(self):
        snapshot = evidence_snapshot_fixture()
        snapshot['editions'][0]['content']['validated'] = False
        self.assertEqual(curate(snapshot, candidate())['manifest']['changes'], [])

    def test_partial_story_citation_set_cannot_issue_import_change(self):
        snapshot = evidence_snapshot_fixture()
        additional = article('second-article')
        snapshot['articles'].append(additional)
        edition = snapshot['editions'][0]
        content = edition['content']
        source = dict(content['sources'][0], id='second-story-source', url=additional['url'])
        content['sources'].append(source)
        content['stories'][0]['sourceIds'].append(source['id'])
        edition['bindings'].append({
            'storyId': content['stories'][0]['id'],
            'rawArticleId': additional['id'],
            'claimKey': 'second-claim',
            'sourceUrl': additional['url'],
        })
        result = curate(snapshot, candidate())
        self.assertEqual(result['manifest']['changes'], [])
        result = curate(snapshot, candidate(evidence=[
            *candidate()['evidence'], {'articleId': additional['id'], 'kind': 'other', 'quote': RETAINED_QUOTE},
        ]))
        self.assertEqual(result['manifest']['changes'][0]['sourceRoles'], {
            'fixture-story-source': 'vendor', 'second-story-source': 'other',
        })

    def test_duplicate_project_keys_and_relabelled_same_stage_evidence_are_rejected(self):
        snapshot = evidence_snapshot_fixture()
        for duplicate in (candidate(), candidate(milestoneKey='another-pilot')):
            with self.subTest(record=duplicate['milestoneKey']), self.assertRaises(TrackerError):
                curate(snapshot, candidate(), duplicate)


if __name__ == '__main__':
    unittest.main()
