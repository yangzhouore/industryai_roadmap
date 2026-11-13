"""Offline daily editorial gates; mocked source snapshots are never news publications."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .live import _normalize_articles, _select, generate_real_issue
from .provider import OpenAIProvider, ProviderError
from .test_live import ARTICLE, ScriptedHTTP, envelope, provider
from ..scoring.events import normalize_event_key
from ..store import Store
from ..verification import validate_issue
from ..verification.review import _seal_review, validate_review
from ..verification.temporal import daily_source_window, publication_time


def recent_article(**changes):
    # Date shifts exercise temporal gates only, not a claim that NIST published on this date.
    return dict(ARTICLE, publishedAt="2026-11-12T12:00:00Z", **changes)


def reseal(draft, review, evidence=None, batches=None):
    return _seal_review(draft, evidence or review["evidence"], review["claims"],
                        review["classifications"], review["factCheck"], review["requests"],
                        daily_window=True, excluded_event_keys=review["excludedEventKeys"],
                        classification_batches=batches or review["classificationBatches"])


class DailyTemporalTests(unittest.TestCase):
    def test_previous_completed_berlin_day_and_unknown_event_are_preserved(self):
        transport = ScriptedHTTP()
        draft, review = generate_real_issue([recent_article()], "2026-11-13", provider(transport), daily_window=True)
        self.assertEqual(draft["id"], "issue-2026-11-13")
        self.assertEqual(review["dailySourceWindow"]["sourceDate"], "2026-11-12")
        self.assertIsNone(draft["sources"][0]["eventAt"])
        self.assertFalse(review["historicalDay"])
        self.assertEqual(validate_issue(draft, review), [])
        for request in transport.requests:
            payload = json.loads(request["input"][0]["content"][0]["text"])
            self.assertEqual(payload["dailySourceWindow"], review["dailySourceWindow"])

    def test_dst_windows_include_23_and_25_hour_days_and_exact_edges(self):
        for issue_date, hours in (("2026-03-30", 23), ("2026-10-26", 25)):
            window = daily_source_window(issue_date)
            start, end = map(publication_time, (window["startInclusive"], window["endExclusive"]))
            self.assertEqual((end - start).total_seconds(), hours * 3600)
            for stamp in (start, end - timedelta(microseconds=1)):
                _normalize_articles([dict(ARTICLE, publishedAt=stamp.isoformat())], issue_date, daily_window=True)
            for stamp in (start - timedelta(microseconds=1), end):
                with self.assertRaisesRegex(ValueError, "previous complete"):
                    _normalize_articles([dict(ARTICLE, publishedAt=stamp.isoformat())], issue_date, daily_window=True)

    def test_conflicting_policies_and_bad_event_timestamp_fail_before_any_call(self):
        transport = ScriptedHTTP()
        for article, options in ((recent_article(), {"strict_day": True, "daily_window": True}),
                                 (recent_article(eventAt="2026-11-12T12:00:00"), {"daily_window": True})):
            with self.assertRaises(ValueError):
                generate_real_issue([article], "2026-11-13", provider(transport), **options)
        self.assertEqual(transport.requests, [])

    def test_known_old_or_future_event_excluded_before_generation(self):
        for event_at in ("2020-01-01T00:00:00Z", "2026-11-13T08:00:00Z"):
            transport = ScriptedHTTP()
            api = provider(transport)
            with self.assertRaisesRegex(ProviderError, "No source-backed"):
                generate_real_issue([recent_article(eventAt=event_at)], "2026-11-13", api, daily_window=True)
            self.assertEqual(len(transport.requests), 1)
            self.assertEqual(api.editorial_trace["rejections"][0]["reason"], "event_outside_daily_window")

    def test_final_receipt_rejects_temporal_evidence_changes(self):
        draft, review = generate_real_issue([recent_article()], "2026-11-13", provider(ScriptedHTTP()), daily_window=True)
        for changes in ({"publishedAt": "2026-11-11T00:00:00Z"}, {"eventAt": "2020-01-01T00:00:00Z"}):
            changed, evidence = deepcopy(draft), deepcopy(review["evidence"])
            changed["sources"][0].update(changes)
            evidence[0].update(changes)
            with self.assertRaisesRegex(ValueError, "review|Review"):
                reseal(changed, review, evidence=evidence)
        tampered = deepcopy(review)
        tampered["dailySourceWindow"]["sourceDate"] = "2026-11-13"
        self.assertTrue(validate_review(draft, tampered))

    def test_normalized_previous_event_is_excluded_and_reason_retained(self):
        transport = ScriptedHTTP()
        api = provider(transport)
        key = "NIST Manufacturing Digital Twin Testbed Research"
        with self.assertRaisesRegex(ProviderError, "No source-backed"):
            generate_real_issue([recent_article()], "2026-11-13", api, daily_window=True,
                                excluded_event_keys=(key,))
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(api.editorial_trace["rejections"][0]["reason"], "previously_published_event")
        self.assertEqual(normalize_event_key("ＮＩＳＴ--TESTBED"), "nist testbed")

    def test_invalid_output_and_incomplete_bilingual_output_fail_closed(self):
        for stage_to_break in ("classify", "generate"):
            def mutate(stage, data):
                if stage == stage_to_break:
                    if stage == "classify":
                        data["classifications"][0].pop("maturity")
                    else:
                        data["stories"][0]["title"]["zh"] = ""
            with self.assertRaises(ProviderError):
                generate_real_issue([recent_article()], "2026-11-13", provider(ScriptedHTTP(mutate)), daily_window=True)

    def test_rejected_review_keeps_private_draft_and_cannot_replace_published_content(self):
        article = recent_article()
        original, review = generate_real_issue([article], "2026-11-13", provider(ScriptedHTTP()), daily_window=True)
        def mutate(stage, data):
            if stage == "verify":
                data["claims"][0].update(supported=False, rationale="Unsupported temporal claim")
        saved = []
        with TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "daily.sqlite"))
            self.assertTrue(store.publish(original, review))
            before = store.published()
            with self.assertRaisesRegex(ValueError, "unsupported"):
                generate_real_issue([article], "2026-11-13", provider(ScriptedHTTP(mutate)), saved.append, daily_window=True)
            self.assertEqual(len(saved), 1)
            self.assertFalse(saved[0]["validated"])
            with self.assertRaises(ValueError):
                store.publish(saved[0], {"approved": True})
            self.assertEqual(store.published(), before)
            self.assertFalse(store.publish(original, review))
            store.close()


class DailyBatchTests(unittest.TestCase):
    @staticmethod
    def articles(count):
        return [dict(recent_article(), url=ARTICLE["url"] + f"?daily-test={n}") for n in range(count)]

    class BatchHTTP(ScriptedHTTP):
        def __init__(self, duplicate_response=False, missing_article=False):
            super().__init__()
            self.counter = 0
            self.duplicate_response = duplicate_response
            self.missing_article = missing_article

        def __call__(self, request):
            stage = request["text"]["format"]["name"].removeprefix("industrial_")
            if stage != "classify":
                return super().__call__(request)
            response = super().__call__(request)
            payload = json.loads(request["input"][0]["content"][0]["text"])
            seed = json.loads(response["output"][0]["content"][0]["text"])["classifications"][0]
            rows = [{**seed, "articleId": article["id"]} for article in payload["articles"]]
            if self.missing_article:
                rows.pop()
            response = envelope({"classifications": rows}, "classify" + ("" if self.duplicate_response else str(self.counter)))
            self.counter += 1
            return response

    def test_all_candidates_classified_in_chunks_before_single_review(self):
        transport = self.BatchHTTP()
        api = provider(transport)
        draft, review = generate_real_issue(self.articles(31), "2026-11-13", api, daily_window=True)
        self.assertEqual(len(transport.requests), 4)
        self.assertEqual([len(batch["articleIds"]) for batch in review["classificationBatches"]], [30, 1])
        self.assertEqual(len(api.editorial_trace["classifications"]), 31)
        self.assertEqual(len(draft["stories"]), 1)  # one event, never manufacture filler
        self.assertEqual(validate_review(draft, review), [])
        incomplete = deepcopy(review["classificationBatches"])
        incomplete[0]["articleIds"] = []
        with self.assertRaisesRegex(ValueError, "batch audit"):
            reseal(draft, review, batches=incomplete)

    def test_duplicate_batch_response_or_incomplete_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError, "batch audit"):
            generate_real_issue(self.articles(31), "2026-11-13", provider(self.BatchHTTP(duplicate_response=True)), daily_window=True)
        with self.assertRaisesRegex(ProviderError, "batch must cover"):
            generate_real_issue(self.articles(31), "2026-11-13", provider(self.BatchHTTP(missing_article=True)), daily_window=True)

    def test_daily_cap_and_legacy_cap_fail_before_calls(self):
        transport = self.BatchHTTP()
        for count, daily in ((301, True), (31, False)):
            with self.assertRaisesRegex(ValueError, "collected articles"):
                generate_real_issue(self.articles(count), "2026-11-13", provider(transport), daily_window=daily)
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
