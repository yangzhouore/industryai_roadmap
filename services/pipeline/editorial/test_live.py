"""Mocked HTTP contract tests; no generated result here is published as news."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from .live import generate_real_issue
from .provider import ENDPOINT, MissingCredentials, OpenAIProvider, ProviderError
from ..verification import SAFE_ANALYSIS, SAFE_LIMITATION, validate_issue, validate_review
from ..verification.review import evidence_text
from ..store import Store

# A short source-backed snapshot of NIST's project page, checked 2026-11-13.
# The page says Created April 15, 2024. Midnight below is test date normalization.
# URL: https://www.nist.gov/programs-projects/digital-twins-advanced-manufacturing
ARTICLE = {"sourceId": "nist", "name": "NIST", "synthetic": False,
           "url": "https://www.nist.gov/programs-projects/digital-twins-advanced-manufacturing",
           "title": "Digital Twins for Advanced Manufacturing",
           "excerpt": "use a NIST Digital Twin Testbed to support research and reference implementations.",
           "publishedAt": "2024-04-15T00:00:00Z", "eventAt": None, "timezone": "UTC"}


def envelope(data, stage):
    return {"id": "resp_test_" + stage, "status": "completed", "output": [
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps(data, ensure_ascii=False)}]}]}


class ScriptedHTTP:
    """Exercises real adapter request/response parsing with injected HTTP replies."""
    def __init__(self, mutate=None):
        self.requests, self.mutate = [], mutate

    def __call__(self, request):
        self.requests.append(deepcopy(request))
        stage = request["text"]["format"]["name"].removeprefix("industrial_")
        payload = json.loads(request["input"][0]["content"][0]["text"])
        if stage == "classify":
            article = payload["articles"][0]
            result = {"classifications": [{"articleId": article["id"], "include": True,
                "category": "Digital Twins & Simulation", "maturity": "research", "company": "NIST",
                "eventKey": "nist-manufacturing-digital-twin-testbed-research", "entities": [{"name": "NIST", "type": "organization"}],
                "dimensions": {"industrial_relevance": .9, "real_deployment": .1, "significance": .5},
                "evidenceQuote": article["excerpt"], "reason": "Manufacturing research plan; no production deployment established."}]}
        elif stage == "generate":
            article = payload["articles"][0]
            fields = {"title": {"en": "NIST plans manufacturing digital twin research", "zh": "NIST规划制造业数字孪生研究"},
                "summary": {"en": "NIST includes a digital twin testbed in its manufacturing research plan.",
                            "zh": "NIST的制造业研究计划包括数字孪生试验台。"},
                "why": deepcopy(SAFE_ANALYSIS), "limitation": deepcopy(SAFE_LIMITATION)}
            original = evidence_text(article)
            pointer = {"articleId": article["id"], "start": 0, "end": len(original), "quote": original}
            claims = [{"field": field, "text": text, "evidence": [deepcopy(pointer)] if field in {"title", "summary"} else []}
                      for field, text in fields.items()]
            result = {"translations": [{"articleId": article["id"], "excerpt": {
                "en": original, "zh": "先进制造业数字孪生\n利用NIST数字孪生试验台支持研究和参考实现。"}}],
                "stories": [{"articleId": article["id"], **fields, "claims": claims}]}
        else:
            result = {"claims": [{"claimId": claim["claimId"], "supported": True,
                        "translationEquivalent": True, "numbersMatch": True, "entitiesMatch": True,
                        "rationale": "The full bilingual claim is supported by the quoted research plan or standard note."}
                       for claim in payload["claims"]],
                "sources": [{"articleId": article["id"], "translationEquivalent": True,
                        "numbersMatch": True, "entitiesMatch": True, "rationale": "Faithful translation of original research plan."}
                       for article in payload["originalEvidence"]],
                "classifications": [{"articleId": item["articleId"], "categorySupported": True,
                        "maturitySupported": True, "companySupported": True, "scoresJustified": True,
                        "rationale": "Research maturity retained and unsupported external evidence scores zero."}
                       for item in payload["classifications"]]}
        if self.mutate:
            self.mutate(stage, result)
        return envelope(result, stage)


def provider(transport):
    return OpenAIProvider(api_key="unit-test-credential", model="test-structured-model",
                          verification_model="test-review-model", transport=transport)


class LiveEditorialTests(unittest.TestCase):
    def test_three_pass_source_backed_draft_and_audit(self):
        transport, drafts = ScriptedHTTP(), []
        draft, review = generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(transport), drafts.append)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(draft["state"], "draft")
        self.assertFalse(draft["validated"])
        self.assertEqual(drafts, [draft])
        self.assertEqual(validate_review(draft, review), [])
        self.assertEqual(validate_issue(draft, review), [])
        self.assertTrue(validate_issue(draft))  # prose is abstractive: a label alone never authorizes it.
        for state in ("validated", "published"):
            self.assertEqual(validate_issue(dict(draft, state=state, validated=True), review), [])
        self.assertNotIn("unit-test-credential", json.dumps(review))
        self.assertEqual(review["classifications"][0]["scoreTrace"]["dimensions"]["authority"], 0)
        self.assertEqual(transport.requests[-1]["model"], "test-review-model")
        for request in transport.requests:
            self.assertFalse(request["store"])
            self.assertTrue(request["text"]["format"]["strict"])
            self.assertNotIn("previous_response_id", request)
        schema = transport.requests[1]["text"]["format"]["schema"]
        self.assertIn("title", schema["$defs"]["GeneratedStory"]["properties"])

    def test_missing_key_fails_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(OpenAIProvider, "_post") as network:
            with self.assertRaises(MissingCredentials):
                generate_real_issue([deepcopy(ARTICLE)], "2026-11-13")
            network.assert_not_called()

    def test_mutated_or_forged_review_cannot_authorize_prose(self):
        draft, review = generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP()))
        fake = deepcopy(review)
        fake["factCheck"]["claims"][0]["supported"] = False
        self.assertTrue(validate_review(draft, fake))
        changed = deepcopy(draft)
        changed["stories"][0]["title"]["en"] += " invented claim"
        self.assertTrue(validate_issue(changed, review))
        fake = {"approved": True, "evidenceStatus": "verified"}
        self.assertTrue(validate_review(draft, fake))
        # Persisted audit cannot be replayed by a later process with a different in-memory seal key.
        with patch("services.pipeline.verification.review._PROCESS_KEY", b"different-process-key"):
            self.assertTrue(validate_review(draft, review))

    def test_missing_claim_check_blocks_but_keeps_draft(self):
        def mutate(stage, data):
            if stage == "verify":
                data["claims"].pop()
        saved = []
        with self.assertRaises((ProviderError, ValueError)):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP(mutate)), saved.append)
        self.assertEqual(len(saved), 1)
        self.assertFalse(saved[0]["validated"])

    def test_independent_rejection_blocks(self):
        def mutate(stage, data):
            if stage == "verify":
                data["claims"][0]["supported"] = False
        with self.assertRaisesRegex(ValueError, "unsupported"):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP(mutate)))

    def test_invalid_source_pointer_blocked_before_review(self):
        def mutate(stage, data):
            if stage == "generate":
                data["stories"][0]["claims"][0]["evidence"][0]["quote"] += ' invented quotation'
        transport = ScriptedHTTP(mutate)
        with self.assertRaisesRegex(ProviderError, "offsets"):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(transport))
        self.assertEqual(len(transport.requests), 2)

    def test_original_evidence_cannot_be_rewritten(self):
        def mutate(stage, data):
            if stage == "generate":
                data["translations"][0]["excerpt"]["en"] += " Invented result."
        with self.assertRaisesRegex(ProviderError, "changed original"):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP(mutate)))

    def test_invented_bilingual_metric_blocks_even_with_overconfident_review(self):
        def mutate(stage, data):
            if stage == "generate":
                field = {"en": "NIST increased output 90%.", "zh": "NIST的产量提高90%。"}
                data["stories"][0]["summary"] = field
                next(c for c in data["stories"][0]["claims"] if c["field"] == "summary")["text"] = field
        with self.assertRaisesRegex(ProviderError, "unsupported figure"):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP(mutate)))

    def test_locale_mismatch_blocks_even_if_reviewer_approves(self):
        def mutate(stage, data):
            if stage == "generate":
                field = {"en": "NIST research", "zh": "研究"}
                data["stories"][0]["summary"] = field
                next(c for c in data["stories"][0]["claims"] if c["field"] == "summary")["text"] = field
        with self.assertRaisesRegex(ProviderError, "entity mismatch"):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP(mutate)))

    def test_irrelevant_articles_do_not_force_filler(self):
        def mutate(stage, data):
            if stage == "classify":
                data["classifications"][0]["include"] = False
        transport = ScriptedHTTP(mutate)
        with self.assertRaisesRegex(ProviderError, "No source-backed"):
            generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(transport))
        self.assertEqual(len(transport.requests), 1)

    def test_synthetic_or_private_evidence_rejected(self):
        for changes in ({"synthetic": True}, {"url": "https://127.0.0.1/report"}, {"url": "https://example.org/fixtures/x"}):
            with self.assertRaises(ValueError):
                generate_real_issue([{**ARTICLE, **changes}], "2026-11-13", provider(ScriptedHTTP()))

    def test_publication_accepts_only_reviewed_content(self):
        draft, review = generate_real_issue([deepcopy(ARTICLE)], "2026-11-13", provider(ScriptedHTTP()))
        with TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "review.sqlite"))
            try:
                with self.assertRaises(ValueError):
                    store.publish(draft)
                self.assertEqual(store.published(), [])
                self.assertTrue(store.publish(draft, review=review))
                self.assertEqual(len(store.published()), 1)
            finally:
                store.close()


class HTTPAdapterTests(unittest.TestCase):
    def test_fixed_endpoint_auth_and_bounded_rate_limit_retry(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps(envelope({"ok": True}, "http")).encode()
        class Opener:
            def __init__(self): self.calls = 0
            def open(self, request, timeout):
                self.calls += 1
                self.request = request
                if self.calls == 1:
                    raise HTTPError(ENDPOINT, 429, "rate limited", {}, io.BytesIO(b"redacted"))
                return Response()
        opener, sleeps = Opener(), []
        real = OpenAIProvider(api_key="unit-test-credential", model="test-model", sleep=sleeps.append)
        with patch("services.pipeline.editorial.provider.build_opener", return_value=opener):
            result = real.complete_json("classify", {"type": "object"}, {}, "test")
        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(opener.calls, 2)
        self.assertEqual(sleeps, [1])
        self.assertEqual(opener.request.full_url, ENDPOINT)
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer unit-test-credential")

    def test_auth_failure_does_not_leak_response_body_or_retry(self):
        class Opener:
            calls = 0
            def open(self, *args, **kwargs):
                self.calls += 1
                raise HTTPError(ENDPOINT, 401, "unauthorized", {}, io.BytesIO(b"unit-test-credential"))
        opener = Opener()
        real = OpenAIProvider(api_key="unit-test-credential", model="test-model")
        with patch("services.pipeline.editorial.provider.build_opener", return_value=opener):
            with self.assertRaisesRegex(ProviderError, "HTTP 401") as caught:
                real.complete_json("classify", {}, {}, "test")
        self.assertNotIn("unit-test-credential", str(caught.exception))
        self.assertEqual(opener.calls, 1)

    def test_refusal_incomplete_and_malformed_output_fail_closed(self):
        variants = [dict(envelope({}, "test"), status="incomplete"),
                    {"status": "completed", "id": "resp_test", "output": [{"type": "message", "role": "assistant",
                     "content": [{"type": "refusal", "refusal": "refused"}]}]},
                    {"status": "completed", "id": "resp_test", "output": [{"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "not-json"}]}]}]
        for response in variants:
            with self.assertRaises(ProviderError):
                provider(lambda request: response).complete_json("generate", {}, {}, "test")


if __name__ == "__main__":
    unittest.main()
