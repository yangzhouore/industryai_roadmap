"""Two-model routing, spend hooks, strict historical time and event regression tests."""
import os
import unittest
from unittest.mock import patch
from .provider import OpenAIProvider, ProviderError
from .live import _normalize_articles, _select, generate_real_issue
from .test_live import ARTICLE, ScriptedHTTP, envelope
from .live_schema import Classified
from ..scoring.events import group_events
from ..verification import validate_issue
from ..verification.temporal import day_bounds


class ModelBudgetTests(unittest.TestCase):
    def test_exact_requested_models_and_low_default(self):
        calls = []
        def transport(request):
            calls.append(request)
            return envelope({"ok": True}, request["text"]["format"]["name"])
        with patch.dict(os.environ, {}, clear=True):
            api = OpenAIProvider(api_key="unit-test-key", transport=transport)
        for stage in ("classify", "generate", "verify"):
            api.complete_json(stage, {"type": "object"}, {}, "test")
        self.assertEqual([call["model"] for call in calls], ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-terra"])
        self.assertEqual([call["reasoning"] for call in calls], [{"effort": "low"}] * 3)

    def test_none_effort_env_honored_and_minimal_rejected(self):
        calls = []
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "none"}, clear=True):
            api = OpenAIProvider(api_key="unit-test-key", transport=lambda request: calls.append(request) or envelope({}, "test"))
            api.complete_json("classify", {}, {}, "test")
        self.assertEqual(calls[0]["reasoning"]["effort"], "none")
        with self.assertRaises(ProviderError):
            OpenAIProvider(api_key="unit-test-key", reasoning_effort="minimal")

    def test_budget_gate_prevents_any_transport_request(self):
        calls = []
        def exhausted(context):
            self.assertEqual(context["stage"], "classify")
            self.assertEqual(context["model"], "gpt-6-luna")
            self.assertEqual(context["maxOutputTokens"], 4096)
            raise RuntimeError("test budget exhausted")
        api = OpenAIProvider(api_key="unit-test-key", max_output_tokens=4096, retries=0,
                             before_request=exhausted, transport=lambda request: calls.append(request))
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            api.complete_json("classify", {}, {}, "test")
        self.assertEqual(calls, [])

    def test_incomplete_response_usage_includes_reasoning_and_notifies_budget(self):
        audit = []
        response = {"id": "resp_incomplete_test", "status": "incomplete", "model": "gpt-6-luna",
                    "output": [], "usage": {"input_tokens": 100, "output_tokens": 4000,
                      "output_tokens_details": {"reasoning_tokens": 3900}, "total_tokens": 4100}}
        api = OpenAIProvider(api_key="unit-test-key", transport=lambda request: response,
                             before_request=lambda context: audit.append(("before", context)),
                             after_response=lambda record: audit.append(("after", record)))
        with self.assertRaisesRegex(ProviderError, "incomplete"):
            api.complete_json("classify", {}, {}, "test")
        self.assertEqual([kind for kind, value in audit], ["before", "after"])
        self.assertEqual(api.usage[0]["reasoningTokens"], 3900)
        self.assertEqual(audit[1][1]["usage"]["output_tokens"], 4000)
        self.assertEqual(audit[1][1]["status"], "incomplete")


class HistoricalDayTests(unittest.TestCase):
    def test_previous_utc_date_inside_berlin_day_is_allowed(self):
        article = dict(ARTICLE, publishedAt="2026-11-12T23:30:00Z")
        normalized = _normalize_articles([article], "2026-11-13", strict_day=True)
        self.assertEqual(len(normalized), 1)
        transport = ScriptedHTTP()
        api = OpenAIProvider(api_key="unit-test-key", transport=transport, retries=0)
        draft, review = generate_real_issue([article], "2026-11-13", api, strict_day=True)
        self.assertEqual(draft["id"], "issue-2026-11-13-historical")
        self.assertTrue(review["historicalDay"])
        self.assertEqual(review["editorialTimezone"], "Europe/Berlin")
        self.assertEqual(validate_issue(draft, review), [])

    def test_next_berlin_day_and_stale_day_are_rejected(self):
        for timestamp in ("2026-11-13T23:00:00Z", "2026-11-12T22:59:59Z"):
            with self.assertRaises(ValueError):
                _normalize_articles([dict(ARTICLE, publishedAt=timestamp)], "2026-11-13", strict_day=True)

    def test_day_boundaries_observe_short_and_long_dst_days(self):
        start, end = day_bounds("2026-03-29")
        self.assertEqual((end - start).total_seconds(), 23 * 3600)
        start, end = day_bounds("2026-10-25")
        self.assertEqual((end - start).total_seconds(), 25 * 3600)


class EventTests(unittest.TestCase):
    def _classification(self, article_id, event_key):
        return {"articleId": article_id, "eventKey": event_key, "include": True,
                "company": "NIST", "category": "Digital Twins & Simulation", "maturity": "research",
                "entities": [{"name": "NIST", "type": "organization"}],
                "dimensions": {"industrial_relevance": .9, "real_deployment": .1, "significance": .5},
                "evidenceQuote": ARTICLE["excerpt"], "reason": "Research evidence"}

    def test_model_cluster_merges_different_headlines_for_same_event(self):
        articles = [{"id": "a", "title": "NIST digital twin testbed"}, {"id": "b", "title": "Manufacturing research priorities"}]
        groups = group_events([self._classification("a", "nist-testbed-event"), self._classification("b", "nist-testbed-event")], articles)
        self.assertEqual(groups["a"], groups["b"])

    def test_code_collapses_near_identical_titles_even_if_model_keys_differ(self):
        articles = [{"id": "a", "title": "NIST launches manufacturing research project"},
                    {"id": "b", "title": "NIST launches manufacturing research project!"}]
        groups = group_events([self._classification("a", "one"), self._classification("b", "two")], articles)
        self.assertEqual(groups["a"], groups["b"])

    def test_same_company_distinct_events_are_preserved(self):
        articles = [{"id": "a", "title": "Digital twin testbed"}, {"id": "b", "title": "Laser metrology uncertainty"}]
        groups = group_events([self._classification("a", "testbed"), self._classification("b", "metrology")], articles)
        self.assertNotEqual(groups["a"], groups["b"])

    def test_duplicate_event_is_selected_once_and_invented_entity_blocks(self):
        originals = _normalize_articles([ARTICLE], "2026-11-13")
        first = originals[0]
        second = {**first, "id": "different-article-id"}
        classified = [self._classification(first["id"], "same-event"), self._classification(second["id"], "same-event")]
        selected = _select(classified, [first, second], "2026-11-13")
        self.assertEqual(len(selected), 1)
        classified[0]["entities"] = [{"name": "InventedCompany", "type": "organization"}]
        rejected=[]
        selected=_select(classified, [first, second], "2026-11-13", rejected)
        self.assertEqual([s['articleId'] for s in selected],[second['id']])
        self.assertEqual(rejected[0]['reason'],'unsupported_entity')
        with self.assertRaisesRegex(ProviderError, 'No source-backed'):
            _select(classified[:1], [first], '2026-11-13')

    def test_unknown_maturity_excludes_only_unsupported_candidate(self):
        original = _normalize_articles([ARTICLE], "2026-11-13")[0]
        unsupported = {**original, "id": "unsupported-article"}
        bad = self._classification(unsupported["id"], "unsupported-event")
        bad["maturity"] = "unknown"
        rejected = []
        selected = _select([bad, self._classification(original["id"], "supported-event")],
                           [unsupported, original], "2026-11-13", rejections=rejected)
        self.assertEqual([entry["articleId"] for entry in selected], [original["id"]])
        self.assertEqual(rejected[0]["reason"], "unsupported_taxonomy")
        self.assertEqual(rejected[0]["maturity"], "unknown")

    def test_all_unknown_candidates_fail_closed_with_trace(self):
        original = _normalize_articles([ARTICLE], "2026-11-13")[0]
        bad = self._classification(original["id"], "unsupported-event")
        bad["maturity"] = "unknown"
        with self.assertRaisesRegex(ProviderError, "maturity=unknown"):
            _select([bad], [original], "2026-11-13")

    def test_excluded_article_can_omit_unknown_identities_without_invention(self):
        original = _normalize_articles([ARTICLE], "2026-11-13")[0]
        excluded = self._classification(original["id"], "")
        excluded.update(include=False, company="", entities=[], category="out_of_scope", maturity="unknown")
        Classified.model_validate({"classifications": [excluded]})
        rejected = []
        with self.assertRaisesRegex(ProviderError, "No source-backed"):
            _select([excluded], [original], "2026-11-13", rejections=rejected)
        self.assertEqual(rejected[0]["reason"], "classifier_excluded")

    def test_included_article_cannot_use_empty_company_event_or_entities(self):
        original = _normalize_articles([ARTICLE], "2026-11-13")[0]
        for changes in ({"company": ""}, {"eventKey": ""}, {"entities": []}):
            included = {**self._classification(original["id"], "supported-event"), **changes}
            Classified.model_validate({"classifications": [included]})
            rejected = []
            with self.assertRaisesRegex(ProviderError, "No source-backed"):
                _select([included], [original], "2026-11-13", rejections=rejected)
            self.assertEqual(rejected[0]["reason"], "missing_supported_identity")


if __name__ == "__main__":
    unittest.main()
