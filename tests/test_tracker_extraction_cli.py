"""Private I/O, offline Responses preparation, cost and review boundary tests."""

import json
from pathlib import Path
import tempfile
import unittest

from services.tracker.extract_candidates import estimate_cost, validate_saved
from services.tracker.extraction_request import request_bundle, response_json
from services.tracker.manifest import Catalog, TrackerError, load_changes


def snapshot():
    articles = [
        {'id': key, 'title': 'Siemens Digital Twins at a fictional site',
         'excerpt': 'Siemens started a pilot using Digital Twins.',
         'publishedAt': '2025-01-16T10:25:00+00:00', 'eventAt': None,
         'url': 'https://example.test/' + key, 'sourceId': 'fixture-source',
         'publisher': 'Fictional vendor', 'sourceTimezone': 'UTC', 'contentHash': '0' * 64}
        for key in ('fixture-b', 'fixture-a')
    ]
    return {'version': 1, 'articles': articles, 'editions': []}


def envelope(payload):
    return {'status': 'completed', 'output': [
        {'type': 'message', 'role': 'assistant', 'status': 'completed',
         'content': [{'type': 'output_text', 'text': json.dumps(payload)}]},
    ]}


def proposal(article):
    return {'projectName': None, 'companyIds': ['siemens'], 'technologyIds': ['digital-twins'],
            'kind': 'pilot', 'stage': 'pilot',
            'evidence': [{'articleId': article, 'quote': 'Siemens started a pilot using Digital Twins.'}]}


class TrackerExtractionCliTests(unittest.TestCase):
    def test_request_is_model_configurable_scoped_and_excludes_source_metadata(self):
        bundle = request_bundle(snapshot(), 'gpt-6-luna')
        self.assertEqual([request['articleId'] for request in bundle['requests']], ['fixture-a', 'fixture-b'])
        request = bundle['requests'][0]['body']
        self.assertEqual(request['model'], 'gpt-6-luna')
        self.assertFalse(request['store'])
        self.assertNotIn('tools', request)
        rendered = json.dumps(request)
        for excluded in ('2025-01-16T10:25:00', 'https://example.test', 'eventAt', 'publishedAt', 'fixture-b'):
            self.assertNotIn(excluded, rendered)
        schema = request['text']['format']['schema']
        evidence = schema['properties']['candidates']['items']['properties']['evidence']['items']
        self.assertEqual(evidence['properties']['articleId']['enum'], ['fixture-a'])
        self.assertFalse(evidence['additionalProperties'])
        data = snapshot()
        data['articles'][0].update(title='Unrelated headline', excerpt='An unrelated claim.', publisher='Siemens')
        publisher_only = request_bundle(data, 'gpt-6-luna', ['fixture-b'])['requests'][0]['body']
        allowed = publisher_only['text']['format']['schema']['properties']['candidates']['items']['properties']['companyIds']
        self.assertEqual(allowed['maxItems'], 0)

    def test_cost_uses_explicit_rates_and_output_budget(self):
        bundle = request_bundle(snapshot(), 'gpt-6.1-terra')
        price = estimate_cost(bundle)
        self.assertEqual(price['inputUsdPerMillion'], '1.00')
        self.assertEqual(price['outputUsdPerMillion'], '5.00')
        self.assertEqual(price['maximumRequestedOutputTokens'], 2400)
        self.assertGreater(float(price['paddedUsdAtFullOutput']), float(price['estimatedUsdAtFullOutput']))
        custom = request_bundle(snapshot(), 'custom-model')
        with self.assertRaises(TrackerError):
            estimate_cost(custom)
        self.assertEqual(estimate_cost(custom, '0.15', '0.90')['outputUsdPerMillion'], '0.90')
        for pair in (('NaN', '0.2'), ('-1', '0.2'), ('0.2', None), ('1e-999999', '0.2')):
            with self.subTest(pair=pair), self.assertRaises(TrackerError):
                estimate_cost(bundle, *pair)

    def test_refused_partial_and_duplicate_json_responses_are_rejected(self):
        good = envelope({'candidates': []})
        self.assertEqual(response_json(good), {'candidates': []})
        refusal = envelope({'candidates': []})
        refusal['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'Untrusted text'}]
        duplicate = envelope({'candidates': []})
        duplicate['output'][0]['content'][0]['text'] = '{"candidates":[],"candidates":[]}'
        for value in (dict(good, status='incomplete'), refusal, duplicate):
            with self.subTest(), self.assertRaises(TrackerError):
                response_json(value)

    def test_saved_response_stays_scoped_and_cannot_be_an_import_manifest(self):
        data = snapshot()
        saved = {'version': 1, 'responses': [
            {'articleId': 'fixture-a', 'response': envelope({'candidates': [proposal('fixture-a'), proposal('fixture-b')]})},
        ]}
        result = validate_saved(data, saved, {'fixture-a', 'fixture-b'})
        self.assertEqual(result['rejected'], 1)
        self.assertEqual(len(result['candidates']), 1)
        row = result['candidates'][0]
        self.assertEqual(row['reviewStatus'], 'pending')
        self.assertEqual(row['evidence'][0]['publishedAt'], '2025-01-16T10:25:00+00:00')
        self.assertIsNone(row['evidence'][0]['eventAt'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'candidate.json'
            path.write_text(json.dumps(result), encoding='utf-8')
            with self.assertRaises(TrackerError):
                load_changes(path, Catalog.load())


if __name__ == '__main__':
    unittest.main()
