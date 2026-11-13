"""Feed-first collection with explicit network permission and deterministic fixtures."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "IndustrialAIDigest/0.1 (+feed-only; local development)"
TRACKERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def canonicalize_url(url):
    if not isinstance(url, str) or any(ord(c) < 33 for c in url) or "\\" in url:
        raise ValueError("Invalid URL characters")
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ValueError("URL must be an absolute HTTP(S) URL without credentials")
    host = parts.hostname.encode("idna").decode().lower().rstrip(".")
    port = parts.port
    host = "[" + host + "]" if ":" in host else host
    authority = host if port is None or (parts.scheme, port) in (("https", 443), ("http", 80)) else f"{host}:{port}"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKERS]
    return urlunsplit((parts.scheme.lower(), authority, parts.path or "/", urlencode(sorted(query)), ""))


def validate_url(url, allowed_hosts, resolver=socket.getaddrinfo):
    canonical = canonicalize_url(url)
    parts = urlsplit(canonical)
    hosts = {host.lower().rstrip(".").encode("idna").decode() for host in allowed_hosts}
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.hostname not in hosts:
        raise ValueError("Network URL must use HTTPS on an explicitly allowed host")
    try:
        addresses = sorted({row[4][0] for row in resolver(parts.hostname, 443, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise ValueError("DNS resolution failed") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Private, reserved or mixed DNS addresses are prohibited")
    return canonical, addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, address, timeout):
        super().__init__(hostname, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


class FeedClient:
    """No proxy inheritance, TLS DNS pinning, fail-closed robots, bounded redirects/retries."""
    def __init__(self, allowed_hosts, timeout=10, retries=2, interval=1.0):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.timeout, self.retries, self.interval = timeout, min(max(retries, 0), 3), max(interval, 1.0)
        self.last_request = {}
        self.audit = []
        self.not_modified = False
        self.response_metadata = {}

    def _request(self, url, max_bytes=2_000_000, robots=None, validators=None):
        original_origin = urlsplit(url).netloc
        for redirect in range(4):
            canonical, addresses = validate_url(url, self.allowed_hosts)
            parts = urlsplit(canonical)
            if parts.netloc != original_origin:
                raise ValueError("Cross-origin redirects require separate source approval")
            if robots is not None and not robots.can_fetch(USER_AGENT, canonical):
                raise ValueError("robots.txt disallows redirect destination")
            wait = self.interval - (time.monotonic() - self.last_request.get(parts.hostname, 0))
            if wait > 0:
                time.sleep(wait)
            self.last_request[parts.hostname] = time.monotonic()
            connection = _PinnedHTTPS(parts.hostname, addresses[0], self.timeout)
            try:
                path = urlunsplit(("", "", parts.path, parts.query, ""))
                headers = {"User-Agent": USER_AGENT,
                                   "Accept": "application/rss+xml, application/atom+xml, text/plain;q=0.5",
                                   "Accept-Encoding": "identity"}
                for field, header in (("etag", "If-None-Match"), ("lastModified", "If-Modified-Since")):
                    value = (validators or {}).get(field)
                    if isinstance(value, str) and len(value) <= 1000 and "\r" not in value and "\n" not in value:
                        headers[header] = value
                connection.request("GET", path, headers=headers)
                response = connection.getresponse()
                metadata = {"url": canonical, "status": response.status,
                            "fetchedAt": datetime.now(timezone.utc).isoformat(),
                            "etag": response.getheader("ETag"),
                            "lastModified": response.getheader("Last-Modified")}
                self.audit.append(metadata)
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError("Redirect missing destination")
                    url = urljoin(canonical, location)
                    continue
                if response.status == 304 and validators:
                    self.not_modified = True
                    self.response_metadata = metadata
                    return b""
                if response.status != 200:
                    raise OSError(f"HTTP status {response.status}")
                if response.getheader("Content-Encoding", "identity") != "identity":
                    raise ValueError("Compressed responses are not accepted")
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise ValueError("Response exceeds collection size limit")
                metadata["bytes"] = len(payload)
                metadata["sha256"] = sha256(payload).hexdigest()
                self.response_metadata = metadata
                return payload
            finally:
                connection.close()
        raise ValueError("Too many redirects")

    def fetch(self, url, *, feed_permitted=False, validators=None):
        if not feed_permitted:
            raise ValueError("Source terms must explicitly permit feed collection")
        canonical, _ = validate_url(url, self.allowed_hosts)
        parts = urlsplit(canonical)
        robots = RobotFileParser()
        robots.parse(self._request(f"https://{parts.netloc}/robots.txt", 100_000).decode("utf-8", "replace").splitlines())
        if not robots.can_fetch(USER_AGENT, canonical):
            raise ValueError("robots.txt disallows collection")
        delay = robots.crawl_delay(USER_AGENT)
        if delay and delay > 60:
            raise ValueError("Source crawl delay exceeds scheduled collector budget")
        self.interval = max(self.interval, delay or 0)
        self.not_modified = False
        for attempt in range(self.retries + 1):
            try:
                return self._request(canonical, robots=robots, validators=validators)
            except (OSError, http.client.HTTPException):
                if attempt == self.retries:
                    raise
                time.sleep(2 ** attempt)


def collect_fixture(issues):
    """Pure offline normalization; duplicates collapse by canonical URL across replays."""
    records = {}
    for issue in issues:
        if issue.get("synthetic") is not True:
            raise ValueError("Fixture collection accepts explicitly synthetic issues only")
        for source in issue.get("sources", []):
            if source.get("synthetic") is not True:
                raise ValueError("Fixture source missing synthetic label")
            item = deepcopy(source)
            item["url"] = canonicalize_url(item["url"])
            parts = urlsplit(item["url"])
            if parts.scheme != "https" or parts.hostname != "example.org" or parts.port is not None or not parts.path.startswith("/fixtures/"):
                raise ValueError("Synthetic source must use reserved https://example.org/fixtures/ URLs")
            item["contentHash"] = sha256(str(sorted(item.get("excerpt", {}).items())).encode()).hexdigest()
            records.setdefault(item["url"], item)
    return sorted(records.values(), key=lambda item: item["url"])


def collect_feed(client, source):
    from services.pipeline.extraction import parse_feed
    from services.pipeline.dedup import deduplicate
    payload = client.fetch(source["feed_url"], feed_permitted=source.get("feed_permitted") is True)
    articles = parse_feed(payload, source["id"], source["name"])
    for article in articles:
        # Do not fetch destination article bodies. Validate links before they enter the registry.
        article["url"], _ = validate_url(article["url"], client.allowed_hosts)
    return deduplicate(articles)
