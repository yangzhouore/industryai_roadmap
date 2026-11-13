"""Fail-closed publication review. Exact extractive claims only in live MVP."""
import ipaddress
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import ValidationError
from .schema import Issue
from ..scoring import CATEGORIES, MATURITY
from ..translation import parity_errors
from .temporal import day_bounds, publication_time

SAFE_ANALYSIS = {
    "en": "Editorial analysis: inspect the workflow, evidence and deployment constraints before drawing conclusions.",
    "zh": "编辑分析：得出结论前，应审视工作流程、证据和部署约束。",
}
SAFE_LIMITATION = {
    "en": "Evidence is limited to the cited sources. Independent deployment validation is not established.",
    "zh": "证据仅限于所引来源，尚未建立独立的部署验证。",
}
SAFE_TITLE = {"en": "Industrial AI Digest", "zh": "工业人工智能简报"}
SAFE_INTRODUCTION = {
    "en": "A source-grounded briefing on industrial AI. Read each cited source and its limitations.",
    "zh": "基于来源的工业人工智能简报。请阅读所引来源及其局限。",
}


def _normal(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_issue(issue: dict, review: dict | None = None) -> list[str]:
    """Return stable errors rather than publishing or mutating data.

    Without a process-verified review receipt, production prose remains extractive.
    A receipt binds independent claim checks to exact issue and source evidence.
    """
    try:
        Issue.model_validate(issue)
    except (ValidationError, TypeError) as error:
        return [f"schema: {error}"]
    errors = []
    reviewed = False
    if review is not None:
        from .review import validate_review
        review_errors = validate_review(issue, review)
        errors.extend(review_errors)
        reviewed = not review_errors
    if issue["state"] in {"validated", "published"} and not issue["validated"]:
        errors.append("state requires validated=true")
    for field in ("title", "introduction"):
        errors.extend(parity_errors(issue[field], field))
        if not issue["synthetic"] and not reviewed:
            safe = SAFE_TITLE if field == "title" else SAFE_INTRODUCTION
            for locale in ("en", "zh"):
                if issue[field][locale] != safe[locale] and not any(_normal(issue[field][locale]) in _normal(s["excerpt"][locale]) for s in issue["sources"]):
                    errors.append(f"{field}.{locale}: unsupported issue claim (use sourced text or standard editorial note)")
    source_map = {s["id"]: s for s in issue["sources"]}
    if len(source_map) != len(issue["sources"]):
        errors.append("duplicate source IDs")
    if len({s["id"] for s in issue["stories"]}) != len(issue["stories"]):
        errors.append("duplicate story IDs")
    companies, categories = set(), set()
    leads = 0
    for source in issue["sources"]:
        try:
            url = urlsplit(source["url"])
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in {None, 443}:
                raise ValueError()
            host = url.hostname.casefold()
            if host in {"localhost", "localhost.localdomain"} or "." not in host or host.endswith((".local", ".internal", ".test", ".invalid")):
                raise ValueError()
            try:
                if not ipaddress.ip_address(host).is_global:
                    raise ValueError("private address")
            except ValueError as error:
                if str(error) == "private address":
                    raise
            reserved = host in {"example.org", "example.com", "example.net"} or host.endswith((".example.org", ".example.com", ".example.net"))
            if source["synthetic"] != issue["synthetic"] or reserved != source["synthetic"]:
                errors.append(f"{source['id']}: synthetic/source URL mismatch")
            if source["synthetic"] and not (host == "example.org" and url.path.startswith("/fixtures/")):
                errors.append(f"{source['id']}: synthetic URL must use fixture namespace")
        except ValueError:
            errors.append(f"{source['id']}: invalid source URL")
        try:
            ZoneInfo(source["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            if source["timezone"] != "UTC":
                errors.append(f"{source['id']}: invalid source timezone")
        if publication_time(source["publishedAt"]) >= day_bounds(issue["date"])[1]:
            errors.append(f"{source['id']}: source published after issue date")
        errors.extend(parity_errors(source["excerpt"], source["id"]))
    for story in issue["stories"]:
        prefix = story["id"]
        if story["category"] not in CATEGORIES or story["maturity"] not in MATURITY:
            errors.append(f"{prefix}: unknown industrial category or maturity")
        if (story["evidenceStatus"] == "synthetic") != issue["synthetic"]:
            errors.append(f"{prefix}: evidence status mismatch")
        if len(set(story["sourceIds"])) != len(story["sourceIds"]):
            errors.append(f"{prefix}: duplicate citations")
        refs = [source_map[s] for s in story["sourceIds"] if s in source_map]
        if len(refs) != len(story["sourceIds"]):
            errors.append(f"{prefix}: unresolved citation")
        for field in ("title", "summary", "why", "limitation"):
            errors.extend(parity_errors(story[field], f"{prefix}.{field}"))
            for locale in ("en", "zh"):
                source_text = " ".join(s["excerpt"][locale] for s in refs)
                if set(re.findall(r"\d+(?:\.\d+)?", story[field][locale])) - set(re.findall(r"\d+(?:\.\d+)?", source_text)):
                    errors.append(f"{prefix}.{field}.{locale}: unsupported figure")
                # Fixture prose is exempt from extractive title checks, never from summary grounding.
                if not reviewed and (field == "summary" or (field == "title" and not issue["synthetic"])):
                    if not any(_normal(story[field][locale]) in _normal(s["excerpt"][locale]) for s in refs):
                        errors.append(f"{prefix}.{field}.{locale}: unsupported claim (must match cited excerpt)")
                if not reviewed and not issue["synthetic"] and field in {"why", "limitation"}:
                    safe = SAFE_ANALYSIS if field == "why" else SAFE_LIMITATION
                    if story[field][locale] != safe[locale] and not any(_normal(story[field][locale]) in _normal(s["excerpt"][locale]) for s in refs):
                        errors.append(f"{prefix}.{field}.{locale}: unsupported claim (use sourced text or standard editorial note)")
        if not issue["synthetic"]:
            if not story["why"]["en"].startswith("Editorial analysis:") or not story["why"]["zh"].startswith("编辑分析："):
                errors.append(f"{prefix}: analysis must be explicitly labeled")
            if not any(story["company"].casefold() in s["excerpt"]["en"].casefold() for s in refs):
                errors.append(f"{prefix}: company absent from evidence")
        if story["kind"] == "feature":
            leads += 1
            if story["company"] in companies or story["category"] in categories:
                errors.append(f"{prefix}: repeated lead company or category")
            companies.add(story["company"])
            categories.add(story["category"])
    if leads > 3:
        errors.append("more than three lead stories")
    return errors


from .review import validate_review
