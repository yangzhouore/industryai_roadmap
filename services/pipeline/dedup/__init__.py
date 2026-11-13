"""Deterministic, replayable source and related-event grouping."""
from difflib import SequenceMatcher
from hashlib import sha256
import re
import unicodedata


def normalize_title(title):
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKC", title).casefold()).split())


def content_hash(article):
    body = article.get("excerpt", "")
    if isinstance(body, dict):
        body = body.get("en", "")
    return sha256((normalize_title(article.get("title", "")) + "\n" + body).encode()).hexdigest()


def deduplicate(articles):
    """Collapse URL/content duplicates and mark syndicated titles as one evidence group."""
    from services.pipeline.collectors import canonicalize_url
    unique, urls, hashes = [], set(), set()
    for original in articles:
        article = dict(original)
        url = canonicalize_url(article["url"])
        digest = content_hash(article)
        if url in urls or digest in hashes:
            continue
        article.update(url=url, contentHash=digest)
        title = normalize_title(article.get("title", ""))
        group = next((old["evidenceGroup"] for old in unique if title and
                      SequenceMatcher(None, title, normalize_title(old.get("title", ""))).ratio() >= .94), None)
        article["evidenceGroup"] = group or sha256(url.encode()).hexdigest()[:16]
        unique.append(article)
        urls.add(url)
        hashes.add(digest)
    return unique


def cluster_events(articles):
    groups = {}
    for article in deduplicate(articles):
        # Related titles are candidate clusters only; editorial review is still required.
        title = normalize_title(article.get("title", ""))
        day = (article.get("eventAt") or article.get("publishedAt") or "")[:10]
        match = next((key for key, items in groups.items() if key.startswith(day + ":") and title and
                      SequenceMatcher(None, title, normalize_title(items[0].get("title", ""))).ratio() >= .80), None)
        key = match or day + ":" + article["evidenceGroup"]
        groups.setdefault(key, []).append(article)
    return groups


def suppress_previously_published(articles, published_urls=(), published_event_keys=()):
    """Exclude repeat evidence or explicitly assigned events, without inferring news.

    Event keys must come from reviewed classifications supplied by the caller.
    Title similarity alone never proves that two historical events are identical.
    """
    from services.pipeline.collectors import canonicalize_url
    urls = {canonicalize_url(url) for url in published_urls}
    event_keys = {key.strip().casefold() for key in published_event_keys if isinstance(key, str) and key.strip()}
    kept, rejected = [], []
    for article in articles:
        url = canonicalize_url(article['url'])
        event_key = article.get('reviewedEventKey') or article.get('eventKey')
        repeated_event = isinstance(event_key, str) and event_key.strip().casefold() in event_keys
        if url in urls or repeated_event:
            rejected.append({'url': url, 'reason': 'previously_published_url' if url in urls else 'previously_published_event'})
        else:
            kept.append(article)
    return kept, rejected
