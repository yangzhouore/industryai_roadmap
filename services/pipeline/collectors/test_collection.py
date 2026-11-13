import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from services.pipeline.collectors import FeedClient, canonicalize_url, collect_fixture, validate_url
from services.pipeline.dedup import cluster_events, deduplicate
from services.pipeline.extraction import excerpt, parse_feed, parse_timestamp


def public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class CollectionTests(unittest.TestCase):
    def test_canonicalization(self):
        self.assertEqual(canonicalize_url("https://EXAMPLE.org:443/feed?utm_source=x&b=2&a=1#fragment"),
                         "https://example.org/feed?a=1&b=2")

    def test_rejects_ambiguous_urls(self):
        for url in ["file:///etc/passwd", "https://user:secret@example.org/", "https://example.org/\r\nx", "https://example.org\\@127.0.0.1/"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonicalize_url(url)

    def test_private_and_mixed_dns_rejected(self):
        for address in ["127.0.0.1", "10.0.0.2", "169.254.169.254", "::1", "192.0.2.1"]:
            resolver = lambda *a, **kw: public_dns() + [(2, 1, 6, "", (address, 443))]
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_url("https://example.org/", {"example.org"}, resolver)

    def test_host_and_scheme_allowlist(self):
        for url in ["http://example.org/", "https://other.org/", "https://example.org:8443/"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url, {"example.org"}, public_dns)
        self.assertEqual(validate_url("https://example.org/", {"example.org"}, public_dns)[1], ["93.184.216.34"])

    def test_fixture_replay_is_idempotent(self):
        path = Path(__file__).resolve().parents[3] / "packages/shared/fixtures/issues.json"
        issues = json.loads(path.read_text(encoding="utf-8"))
        first = collect_fixture(issues)
        self.assertEqual(first, collect_fixture(issues + issues))
        self.assertEqual(len(first), 9)
        self.assertEqual(first[0]["id"], issues[-1]["sources"][0]["id"])

    def test_fixture_cannot_impersonate_real_news(self):
        with self.assertRaises(ValueError):
            collect_fixture([{"synthetic": False, "sources": []}])

    def test_excerpt_removes_markup_and_script(self):
        self.assertEqual(excerpt("<p>Hello</p><script>bad()</script><b>world</b>"), "Hello world")

    def test_rss_dates_separate_from_event(self):
        rss = b"<rss><channel><item><title>Robot test</title><link>https://example.org/a</link><pubDate>Wed, 12 Nov 2025 10:00:00 +0800</pubDate><description>Small excerpt</description></item></channel></rss>"
        article = parse_feed(rss, "demo", "Demo")[0]
        self.assertEqual(article["publishedAt"], "2025-11-12T02:00:00Z")
        self.assertIsNone(article["eventAt"])
        self.assertIn("+0800", article["sourcePublishedAt"])

    def test_atom(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test</title><link href="https://example.org/a"/><updated>2025-11-12T10:00:00Z</updated><summary>Brief</summary></entry></feed>'
        self.assertEqual(parse_feed(atom, "demo", "Demo")[0]["title"], "Test")

    def test_unsafe_xml_and_naive_date(self):
        with self.assertRaises(ValueError):
            parse_feed(b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>', "a", "a")
        with self.assertRaises(ValueError):
            parse_timestamp("2025-11-12T10:00:00")
        with self.assertRaises(ValueError):
            parse_feed('<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>'.encode("utf-16"), "a", "a")

    def test_duplicate_and_syndicated_evidence(self):
        article = {"url": "https://example.org/a", "title": "A robot learns a task", "excerpt": "One", "publishedAt": "2025-11-12T00:00:00Z"}
        copy = dict(article, url="https://example.org/a?utm_source=other")
        syndicated = dict(article, url="https://example.org/b", excerpt="Another excerpt")
        result = deduplicate([article, copy, syndicated])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["evidenceGroup"], result[1]["evidenceGroup"])
        self.assertEqual(len(cluster_events([article, syndicated])), 1)

    def test_missing_source_permission_blocks_network(self):
        with self.assertRaises(ValueError):
            FeedClient({"example.org"}).fetch("https://example.org/feed")

    def test_retry_is_bounded(self):
        client = FeedClient({"example.org"}, retries=2)
        with patch("services.pipeline.collectors.validate_url", return_value=("https://example.org/feed", ["93.184.216.34"])), \
             patch.object(client, "_request", side_effect=[b"User-agent: *\nAllow: /", OSError("temporary"), OSError("temporary"), b"feed"]) as request, \
             patch("services.pipeline.collectors.time.sleep"):
            self.assertEqual(client.fetch("https://example.org/feed", feed_permitted=True), b"feed")
            self.assertEqual(request.call_count, 4)

    def test_robots_denial_blocks_feed_request(self):
        client = FeedClient({"example.org"})
        with patch("services.pipeline.collectors.validate_url", return_value=("https://example.org/feed", ["93.184.216.34"])), \
             patch.object(client, "_request", return_value=b"User-agent: *\nDisallow: /feed") as request:
            with self.assertRaises(ValueError):
                client.fetch("https://example.org/feed", feed_permitted=True)
            self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
