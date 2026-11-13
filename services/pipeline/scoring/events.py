"""Conservative event grouping: duplicate reports never become separate stories."""
from difflib import SequenceMatcher
import re
import unicodedata


def _words(value):
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKC", value).casefold()).split())


def group_events(classifications, articles):
    """Return a stable group label per article using model and original-source signals.

    The model must reuse eventKey for the same announcement even across publishers.
    Code also merges known syndication groups and high-similarity original titles.
    Common organization alone never merges unrelated events.
    """
    inputs = {article["id"]: article for article in articles}
    ordered = sorted(classifications, key=lambda row: row["articleId"])
    parent = {row["articleId"]: row["articleId"] for row in ordered}
    def find(key):
        while parent[key] != key:
            key = parent[key]
        return key
    def union(left, right):
        a, b = sorted((find(left), find(right)))
        parent[b] = a
    for position, left in enumerate(ordered):
        for right in ordered[position + 1:]:
            a, b = inputs[left["articleId"]], inputs[right["articleId"]]
            same_key = _words(left["eventKey"]) == _words(right["eventKey"])
            known = bool(a.get("evidenceGroup")) and a.get("evidenceGroup") == b.get("evidenceGroup")
            titles = SequenceMatcher(None, _words(a["title"]), _words(b["title"])).ratio() >= .80
            if same_key or known or titles:
                union(left["articleId"], right["articleId"])
    return {row["articleId"]: find(row["articleId"]) for row in ordered}
