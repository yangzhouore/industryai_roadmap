"""Evidence-bound, process-local review receipts. Persisted JSON is audit, not authority."""
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import secrets

_PROCESS_KEY = secrets.token_bytes(32)
FIELDS = ("title", "summary", "why", "limitation")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def issue_digest(issue):
    return sha256(canonical({k: v for k, v in issue.items() if k not in {"state", "validated"}})).hexdigest()


def evidence_text(article):
    return article["title"].strip() + "\n" + article["excerpt"].strip()


def _seal_review(issue, evidence, claims, classifications, fact_check, requests, *, strict_day=False):
    """Called only after independent provider output and deterministic checks pass."""
    review = {"version": "industrial-review-v2", "issueHash": issue_digest(issue),
              "evidenceHash": sha256(canonical(evidence)).hexdigest(), "evidence": evidence,
              "claims": claims, "classifications": classifications, "factCheck": fact_check,
              "requests": requests, "historicalDay": bool(strict_day), "editorialTimezone": "Europe/Berlin",
              "reviewedAt": datetime.now(timezone.utc).isoformat()}
    errors = _content_errors(issue, review)
    if errors:
        raise ValueError("Review rejected: " + "; ".join(errors))
    review["seal"] = hmac.new(_PROCESS_KEY, canonical(review), "sha256").hexdigest()
    return review


def validate_review(issue, review):
    """Reject forged, mutated, partial or previous-process review artifacts."""
    if not isinstance(review, dict) or not isinstance(review.get("seal"), str):
        return ["review: missing process-verified artifact"]
    try:
        payload = {k: v for k, v in review.items() if k != "seal"}
        expected = hmac.new(_PROCESS_KEY, canonical(payload), "sha256").hexdigest()
        if not hmac.compare_digest(expected, review["seal"]):
            return ["review: invalid or expired process-local verification seal"]
        return _content_errors(issue, review)
    except (KeyError, TypeError, ValueError, OverflowError):
        return ["review: malformed artifact"]


def _unique_index(items, key):
    index = {item[key]: item for item in items}
    if len(index) != len(items):
        raise ValueError("duplicate review entries")
    return index


def _content_errors(issue, review):
    from pydantic import ValidationError
    from ..editorial.live_schema import FactCheck
    from . import SAFE_ANALYSIS, SAFE_LIMITATION
    errors = []
    if review["version"] != "industrial-review-v2" or issue["synthetic"]:
        return ["review: wrong version or synthetic issue"]
    if issue_digest(issue) != review["issueHash"]:
        errors.append("review: issue content has changed since verification")
    if sha256(canonical(review["evidence"])).hexdigest() != review["evidenceHash"]:
        errors.append("review: input evidence hash mismatch")
    if review.get("historicalDay"):
        from .temporal import publication_day
        if any(publication_day(article["publishedAt"]) != issue["date"] for article in review["evidence"]):
            errors.append("review: historical evidence crossed the exact Europe/Berlin edition day")
    requests = _unique_index(review["requests"], "stage")
    if set(requests) != {"classify", "generate", "verify"} or len({r["responseId"] for r in requests.values()}) != 3:
        errors.append("review: three separate classification/generation/verification responses required")
    for request in requests.values():
        if not request.get("model") or not str(request.get("responseId", "")).startswith("resp_"):
            errors.append("review: missing provider audit metadata")
    try:
        FactCheck.model_validate(review["factCheck"])
    except ValidationError:
        return errors + ["review: malformed independent fact-check output"]
    articles = _unique_index(review["evidence"], "id")
    sources = _unique_index(issue["sources"], "id")
    if set(articles) != set(sources):
        errors.append("review: source/evidence coverage mismatch")
    for source_id, source in sources.items():
        article = articles.get(source_id)
        if not article:
            continue
        for field in ("name", "url", "publishedAt", "eventAt", "timezone", "synthetic"):
            if source[field] != article[field]:
                errors.append(f"review: {source_id} original source metadata changed")
        language = article["language"]
        if source["excerpt"][language] != evidence_text(article):
            errors.append(f"review: {source_id} original source excerpt changed")
    claims = _unique_index(review["claims"], "claimId")
    expected_claims = set()
    for story in issue["stories"]:
        for field in FIELDS:
            claim_id = f"{story['id']}:{field}"
            expected_claims.add(claim_id)
            claim = claims.get(claim_id)
            if not claim or claim.get("storyId") != story["id"] or claim.get("field") != field or claim.get("text") != story[field]:
                errors.append(f"review: {claim_id} missing or changed claim")
                continue
            safe = SAFE_ANALYSIS if field == "why" else SAFE_LIMITATION if field == "limitation" else None
            if not claim["evidence"] and claim["text"] != safe:
                errors.append(f"review: {claim_id} has no source pointers")
            for pointer in claim["evidence"]:
                article = articles.get(pointer["articleId"])
                if not article or pointer["articleId"] not in story["sourceIds"]:
                    errors.append(f"review: {claim_id} refers to an uncited source")
                    continue
                text = evidence_text(article)
                start, end = pointer["start"], pointer["end"]
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text) or text[start:end] != pointer["quote"]:
                    errors.append(f"review: {claim_id} quote pointer does not match original evidence")
    if set(claims) != expected_claims:
        errors.append("review: complete exact claim coverage required")
    checks = _unique_index(review["factCheck"]["claims"], "claimId")
    if set(checks) != expected_claims:
        errors.append("review: independent fact-check omitted or added claims")
    for check in checks.values():
        if not all(check[k] for k in ("supported", "translationEquivalent", "numbersMatch", "entitiesMatch")):
            errors.append(f"review: unsupported or inconsistent claim {check['claimId']}")
    for section, flags in (("sources", ("translationEquivalent", "numbersMatch", "entitiesMatch")),
                           ("classifications", ("categorySupported", "maturitySupported", "companySupported", "scoresJustified"))):
        checks = _unique_index(review["factCheck"][section], "articleId")
        if set(checks) != set(articles):
            errors.append(f"review: incomplete independent {section} checks")
        if any(not all(check[k] for k in flags) for check in checks.values()):
            errors.append(f"review: failed independent {section} check")
    classes = _unique_index(review["classifications"], "articleId")
    if set(classes) != set(articles):
        errors.append("review: classification coverage mismatch")
    event_groups = [entry.get("eventGroup") for entry in classes.values()]
    if any(group is None for group in event_groups) or len(set(event_groups)) != len(event_groups):
        errors.append("review: duplicate or missing reviewed event groups")
    for story in issue["stories"]:
        if len(story["sourceIds"]) != 1 or story["sourceIds"][0] not in classes:
            errors.append("review: reviewed story must retain its classified primary source")
            continue
        classified = classes[story["sourceIds"][0]]
        if any(story[k] != classified[k] for k in ("category", "maturity", "company")):
            errors.append("review: reviewed classification changed")
    return errors
