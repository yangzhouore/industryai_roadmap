"""Pluggable editorial preparation; deterministic mock performs no API calls."""
from copy import deepcopy
from typing import Protocol
from ..scoring import select_stories
from ..verification import validate_issue


class EditorialProvider(Protocol):
    def generate(self, issue: dict) -> dict: ...


class MockProvider:
    """Copy provided bilingual evidence. This provider does not invent news."""
    def generate(self, issue: dict) -> dict:
        return deepcopy(issue)


def prepare_issue(issue: dict, provider: EditorialProvider | None = None) -> dict:
    # Validate before selecting so a malformed story cannot be silently discarded.
    errors = validate_issue(issue)
    if errors:
        raise ValueError("Issue rejected: " + "; ".join(errors))
    draft = (provider or MockProvider()).generate(deepcopy(issue))
    errors = validate_issue(draft)
    if errors:
        raise ValueError("Provider output rejected: " + "; ".join(errors))
    draft["stories"] = select_stories(draft["stories"])
    draft["state"] = "draft"
    draft["validated"] = False
    errors = validate_issue(draft)
    if errors:
        raise ValueError("Issue rejected: " + "; ".join(errors))
    return draft
