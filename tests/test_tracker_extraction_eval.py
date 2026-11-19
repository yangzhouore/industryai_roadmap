"""Offline end-to-end extraction cases using an entirely invented corpus."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from services.tracker.extraction_eval import evaluate, offline_predictions
from services.tracker.extraction_validation import validate_candidates
from services.tracker.manifest import TrackerError


FIXTURE = Path(__file__).resolve().parents[1] / 'services/tracker/fixtures/extraction.json'


class TrackerExtractionEvaluationTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.snapshot = fixture['snapshot']
        self.gold = fixture['gold']
        self.predictions = offline_predictions(self.snapshot)
        self.validated = validate_candidates(self.snapshot, self.predictions)

    def test_offline_fixture_validates_against_all_eight_cases(self):
        metrics = evaluate(self.snapshot, self.gold, self.validated)
        self.assertEqual(metrics['cases'], 8)
        self.assertEqual(metrics['predictedCases'], 8)
        self.assertEqual(metrics['expectedSupported'], 3)
        self.assertEqual(metrics['expectedUnresolved'], 5)
        self.assertEqual(metrics['stageAccuracy'], 1)
        self.assertEqual(metrics['kindAccuracy'], 1)
        self.assertEqual(metrics['supportedPrecision'], 1)
        self.assertEqual(metrics['supportedRecall'], 1)
        self.assertEqual(metrics['unresolvedRecall'], 1)
        self.assertEqual(metrics['canonicalEvidenceCases'], 8)
        self.assertEqual(metrics['canonicalDateCases'], 8)
        self.assertTrue(all(row['reviewStatus'] == 'pending' for row in self.validated['candidates']))

    def test_predictions_repeat_and_use_only_explicit_project_names(self):
        reversed_snapshot = dict(self.snapshot, articles=list(reversed(self.snapshot['articles'])))
        self.assertEqual(offline_predictions(reversed_snapshot), self.predictions)
        first = self.predictions['candidates'][0]
        self.assertEqual(first['projectName'], 'Lumen Bench')
        self.assertEqual(first['companyIds'], ['nvidia'])
        self.assertEqual(first['technologyIds'], ['physical-ai'])
        self.assertIsNone(self.predictions['candidates'][1]['projectName'])
        selected = offline_predictions(self.snapshot, ['fixture-article-3'])
        self.assertEqual(selected['candidates'], [self.predictions['candidates'][2]])
        with self.assertRaises(TrackerError):
            offline_predictions(self.snapshot, ['unknown-article'])

    def test_missing_or_ambiguous_rows_do_not_count_as_correct_unresolved(self):
        altered = deepcopy(self.validated)
        rows = altered['candidates']
        by_article = {row['evidence'][0]['articleId']: row for row in rows}
        rows.remove(by_article['fixture-article-4'])
        rows.append(deepcopy(by_article['fixture-article-5']))
        result = evaluate(self.snapshot, self.gold, altered)
        self.assertEqual(result['predictedCases'], 6)
        self.assertEqual(result['ambiguousCases'], 1)
        self.assertEqual(result['unresolvedRecall'], 0.6)
        self.assertEqual(result['stageAccuracy'], 0.75)

    def test_evaluation_checks_publication_and_event_dates_separately(self):
        altered = deepcopy(self.validated)
        for row in altered['candidates']:
            if row['evidence'][0]['articleId'] == 'fixture-article-2':
                row['evidence'][0]['eventAt'] = row['evidence'][0]['publishedAt']
                break
        metrics = evaluate(self.snapshot, self.gold, altered)
        self.assertEqual(metrics['canonicalDateCases'], 7)
        self.assertEqual(metrics['canonicalEvidenceCases'], 8)
        self.assertEqual(metrics['stageMatches'], 8)

    def test_evaluation_rejects_duplicate_gold_article_sets(self):
        invalid = deepcopy(self.gold)
        invalid['candidates'].append(invalid['candidates'][0])
        with self.assertRaises(TrackerError):
            evaluate(self.snapshot, invalid, self.validated)


if __name__ == '__main__':
    unittest.main()
