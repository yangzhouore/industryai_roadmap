import json
from copy import deepcopy
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from services.pipeline.editorial import prepare_issue
from services.pipeline.scoring import score_story, select_stories
from services.pipeline.verification import SAFE_ANALYSIS, SAFE_LIMITATION, SAFE_TITLE, SAFE_INTRODUCTION, validate_issue
from services.pipeline.store import Store


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((Path(__file__).resolve().parents[3] / "packages/shared/fixtures/issues.json").read_text(encoding="utf-8"))[0]

    def setUp(self):
        self.issue = deepcopy(self.fixture)

    def test_fixture_valid_and_preparation_does_not_mutate(self):
        self.assertEqual(validate_issue(self.issue), [])
        prepared = prepare_issue(self.issue)
        self.assertEqual(prepared["state"], "draft")
        self.assertFalse(prepared["validated"])
        self.assertEqual(self.issue, self.fixture)
        self.assertLessEqual(sum(s["kind"] == "feature" for s in prepared["stories"]), 3)

    def test_unsupported_summary_blocks(self):
        self.issue["stories"][0]["summary"]["en"] = "The factory has deployed a powerful system."
        self.assertTrue(any("unsupported claim" in e for e in validate_issue(self.issue)))
        with self.assertRaises(ValueError):
            prepare_issue(self.issue)

    def test_matching_invented_metric_still_blocks(self):
        self.issue["stories"][0]["summary"] = {"en": "Output improved 50%.", "zh": "产量提高50%。"}
        self.assertTrue(any("unsupported figure" in e for e in validate_issue(self.issue)))

    def test_locale_number_and_entity_mismatch(self):
        self.issue["stories"][0]["title"] = {"en": "GPU 42", "zh": "设备41"}
        errors = validate_issue(self.issue)
        self.assertTrue(any("numerical mismatch" in e for e in errors))
        self.assertTrue(any("entity mismatch" in e for e in errors))

    def test_fabricated_source_and_missing_reference(self):
        self.issue["sources"][0]["url"] = "https://fake-news.example/report"
        self.issue["stories"][0]["sourceIds"] = ["invented"]
        errors = validate_issue(self.issue)
        self.assertTrue(any("mismatch" in e for e in errors))
        self.assertTrue(any("unresolved citation" in e for e in errors))

    def test_real_issue_cannot_use_synthetic_evidence(self):
        self.issue["synthetic"] = False
        self.assertTrue(validate_issue(self.issue))

    def test_private_source_and_future_coverage_blocked(self):
        self.issue["sources"][0]["url"] = "https://127.0.0.1/fixture"
        self.issue["sources"][1]["publishedAt"] = "2099-01-01T00:00:00Z"
        errors = validate_issue(self.issue)
        self.assertTrue(any("invalid source URL" in e for e in errors))
        self.assertTrue(any("after issue date" in e for e in errors))

    def test_malformed_and_unknown_fields(self):
        self.issue["validated"] = "yes"
        self.assertTrue(validate_issue(self.issue)[0].startswith("schema:"))
        self.issue = deepcopy(self.fixture)
        self.issue["stories"][0]["newClaim"] = "unsupported"
        self.assertTrue(validate_issue(self.issue)[0].startswith("schema:"))

    def test_provider_output_checked(self):
        class BadProvider:
            def generate(self, issue):
                issue["stories"][0]["summary"]["en"] = "Invented fact"
                return issue
        with self.assertRaises(ValueError):
            prepare_issue(self.issue, BadProvider())

    def test_live_extractive_gate_and_unsourced_analysis(self):
        # Test data only: verifies the non-synthetic gate without any live request.
        self.issue["synthetic"] = False
        self.issue["title"] = deepcopy(SAFE_TITLE)
        self.issue["introduction"] = deepcopy(SAFE_INTRODUCTION)
        for source in self.issue["sources"]:
            source["synthetic"] = False
            source["url"] = "https://www.nist.gov/"
            source["excerpt"]["en"] += " Evidence subject: TestLab."
            source["excerpt"]["zh"] += " 证据主体：TestLab。"
        for story in self.issue["stories"]:
            source = next(s for s in self.issue["sources"] if s["id"] == story["sourceIds"][0])
            story["title"] = deepcopy(source["excerpt"])
            story["summary"] = deepcopy(source["excerpt"])
            story["company"] = "TestLab" + story["id"]
            source["excerpt"]["en"] += " " + story["company"]
            source["excerpt"]["zh"] += " " + story["company"]
            story["evidenceStatus"] = "verified"
            story["why"] = deepcopy(SAFE_ANALYSIS)
            story["limitation"] = deepcopy(SAFE_LIMITATION)
        self.assertEqual(validate_issue(self.issue), [])
        changed = deepcopy(self.issue)
        changed["title"] = {"en": "Production increased 500%", "zh": "产量提高500%"}
        self.assertTrue(any("unsupported issue claim" in e for e in validate_issue(changed)))
        self.issue["stories"][0]["why"]["en"] = "Editorial analysis: This factory leads the market."
        self.assertTrue(any("unsupported claim" in e for e in validate_issue(self.issue)))

    def test_ranking_trace_and_diversity(self):
        trace = score_story(self.issue["stories"][0])
        self.assertEqual(sum(trace["weights"].values()), 100)
        self.assertEqual(trace["dimensions"]["authority"], 0)
        duplicate = deepcopy(self.issue["stories"][0])
        duplicate["id"] = "another"
        result = select_stories([self.issue["stories"][0], duplicate])
        self.assertEqual(sum(s["kind"] == "feature" for s in result), 1)
        with self.assertRaises(ValueError):
            score_story({**duplicate, "scoringDimensions": {"authority": float("nan")}})

    def test_midway_validation_failure_rolls_back_new_edition(self):
        with TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "rollback.sqlite"))
            try:
                with patch("services.pipeline.verification.validate_issue", side_effect=[[], ["injected validation failure"]]):
                    with self.assertRaisesRegex(ValueError, "injected validation failure"):
                        store.publish(self.issue)
                self.assertEqual(store.execute("SELECT COUNT(*) FROM issues").fetchone()[0], 0)
                self.assertEqual(store.published(), [])
                # A failed transaction must leave the connection usable.
                self.assertTrue(store.publish(self.issue))
                self.assertEqual(len(store.published()), 1)
            finally:
                store.close()

    def test_midway_failure_restores_existing_draft(self):
        with TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "rollback.sqlite"))
            original = dict(self.issue, state="draft", validated=False)
            payload = json.dumps(original, ensure_ascii=False)
            try:
                with store.db:
                    store.execute("INSERT INTO issues(id,slug,issue_date,state,validated,content) VALUES(?,?,?,?,?,?)",
                                  (original["id"], original["slug"], original["date"], "draft", False, payload))
                # Fail immediately before final publication after validated UPDATE.
                with patch("services.pipeline.verification.validate_issue", side_effect=[[], [], ["injected publication failure"]]):
                    with self.assertRaisesRegex(ValueError, "injected publication failure"):
                        store.publish(self.issue)
                row = store.execute("SELECT state,validated,content,published_at FROM issues").fetchone()
                self.assertEqual(row, ("draft", 0, payload, None))
                self.assertEqual(store.published(), [])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
