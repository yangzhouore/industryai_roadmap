"""Bounded feed parsing; descriptions are excerpts, never article bodies."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import xml.etree.ElementTree as ET


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def excerpt(value, limit=400):
    parser = _Text()
    parser.feed(value or "")
    return " ".join(" ".join(parser.parts).split())[:limit]


def parse_timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid publication timestamp") from None
    if dt.tzinfo is None:
        raise ValueError("Source timestamp must include timezone")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_feed(payload, source_id, source_name, max_items=100):
    if len(payload) > 2_000_000 or b"\x00" in payload or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("Unsafe or oversized XML")
    root = ET.fromstring(payload)
    atom = "{http://www.w3.org/2005/Atom}"
    entries = root.findall("./channel/item") or root.findall(atom + "entry")
    language = root.findtext("./channel/language") or root.get("{http://www.w3.org/XML/1998/namespace}lang") or "und"
    articles = []
    for item in entries[:max_items]:
        is_atom = item.tag == atom + "entry"
        ns = atom if is_atom else ""
        original_title = item.findtext(ns + "title") or ""
        title = excerpt(original_title)
        if is_atom:
            links = [node.get("href") for node in item.findall(atom + "link")
                     if node.get("rel", "alternate") == "alternate"]
            url = next((link for link in links if link), None)
        else:
            url = item.findtext("link")
        if not title or not url:
            continue
        raw_date = (item.findtext(ns + "published") or item.findtext(ns + "updated")) if is_atom else (item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date"))
        published_at = parse_timestamp(raw_date)
        body = item.findtext(ns + "summary") if is_atom else item.findtext("description")
        authors = [excerpt(node.findtext(atom + "name")) for node in item.findall(atom + "author")] if is_atom else [excerpt(item.findtext("{http://purl.org/dc/elements/1.1/}creator") or item.findtext("author"))]
        articles.append({"sourceId": source_id, "name": source_name, "url": url.strip(),
                         "title": title, "originalTitle": excerpt(original_title, 2000),
                         "authors": [author for author in authors if author], "language": language,
                         "originalUrl": url.strip(), "excerpt": excerpt(body), "publishedAt": published_at,
                         "sourcePublishedAt": raw_date, "sourceUpdatedAt": item.findtext(atom + "updated") if is_atom else None,
                         "publicationDateBasis": ("atom_published" if item.findtext(atom + "published") else "atom_updated_fallback") if is_atom else ("rss_pubDate" if item.findtext("pubDate") else "rss_dc_date"),
                         "eventAt": None, "eventDateStatus": "not_provided",
                         "timezone": "UTC" if published_at else None, "synthetic": False})
    return articles
