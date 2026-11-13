"""Read-only registry/archive diagnostics; never imports or publishes articles.

The default report uses dated checked-in evidence, without network or credentials.
An explicit --fetch checks only configured feed endpoints under existing policies.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

from . import canonicalize_url

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[2]
FLAGS = ('feed_permitted', 'policy_reviewed', 'excerpt_permitted')
FIELDS = ('name', 'homepage', 'feed_url', 'allowed_hosts',
          'policy_evidence', 'policy_checked_at')


def _registry(path):
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(payload, dict) or not isinstance(payload.get('sources'), list):
        raise ValueError('Registry requires a sources array')
    return payload['sources']


def _safe_url(value):
    try:
        return canonicalize_url(value)
    except (ValueError, TypeError, AttributeError):
        return None


def source_inventory(registry_path):
    """Return every configured source, including blocked/disabled entries.

    This validates declarations, not permission freshness or endpoint availability.
    Invalid raw URLs are deliberately omitted rather than echoed into reports.
    """
    sources, seen = [], set()
    for position, source in enumerate(_registry(registry_path)):
        if not isinstance(source, dict):
            sources.append({'id': f'invalid-{position}', 'status': 'blocked',
                            'missingFields': ['source_object'], 'endpoints': []})
            continue
        source_id = source.get('id')
        missing = []
        if not isinstance(source_id, str) or not source_id.strip():
            source_id = f'invalid-{position}'
            missing.append('id')
        if source_id in seen:
            missing.append('unique_id')
        seen.add(source_id)
        active = source.get('active') is True
        item = {'id': source_id, 'name': source.get('name', source_id),
                'active': active, 'status': 'disabled', 'endpoints': []}
        if not active:
            item['reason'] = source.get('disabled_reason', 'Not enabled in registry')
            sources.append(item)
            continue
        missing.extend(field for field in FIELDS if not source.get(field))
        missing.extend(flag for flag in FLAGS if source.get(flag) is not True)
        if source.get('synthetic') is not False:
            missing.append('synthetic=false')
        hosts = source.get('allowed_hosts', [])
        if not isinstance(hosts, list) or not hosts or not all(isinstance(h, str) for h in hosts):
            hosts = []
            missing.append('valid_allowed_hosts')
        for field in ('homepage', 'feed_url'):
            value = _safe_url(source.get(field))
            parts = urlsplit(value) if value else None
            if not parts or parts.scheme != 'https' or parts.port not in (None, 443) or parts.hostname not in hosts:
                missing.append('approved_' + field)
            elif parts.hostname in {'example.com', 'example.org', 'example.net'} or parts.hostname.endswith(('.example.com', '.example.org', '.example.net')):
                missing.append('real_' + field)
        archives = source.get('archive_feeds', [])
        if not isinstance(archives, list):
            archives = []
            missing.append('archive_feeds_array')
        for endpoint in [source.get('feed_url'), *archives]:
            canonical = _safe_url(endpoint)
            parts = urlsplit(canonical) if canonical else None
            if not parts or parts.scheme != 'https' or parts.port not in (None, 443) or parts.hostname not in hosts:
                missing.append('approved_archive_endpoint')
                continue
            if canonical not in item['endpoints']:
                item['endpoints'].append(canonical)
        item.update(status='blocked' if missing else 'ready',
                    missingFields=sorted(set(missing)),
                    policyCheckedAt=source.get('policy_checked_at'),
                    policyScope=source.get('policy_scope'))
        sources.append(item)
    # A duplicate cannot cause the probe's ID lookup to substitute another policy.
    duplicates = {item['id'] for item in sources if sum(other['id'] == item['id'] for other in sources) > 1}
    for item in sources:
        if item['id'] in duplicates:
            item.update(status='blocked', missingFields=sorted(set(item.get('missingFields', []) + ['unique_id'])))
    groups = {key: [s for s in sources if s['status'] == status]
              for key, status in (('readySources', 'ready'), ('blockedSources', 'blocked'),
                                  ('disabledSources', 'disabled'))}
    return {'sources': sources, **groups,
            'counts': {key: len(value) for key, value in groups.items()},
            'availability': 'Registry declarations only; use explicit fetch for current endpoint checks'}


def _days(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first.isoformat() != start or last.isoformat() != end or not 0 <= (last-first).days <= 62:
        raise ValueError('Window must use YYYY-MM-DD, ordered and at most 63 days')
    return [(first + timedelta(days=offset)).isoformat() for offset in range((last-first).days+1)]


def probe_archives(registry_path, start='2026-11-01', end='2026-11-13', fetch=False):
    """Investigate permitted archives without database access or AI generation."""
    days = _days(start, end)
    inventory = source_inventory(registry_path)
    prior = json.loads((EVIDENCE / 'historical_backfill_evidence.json').read_text(encoding='utf-8'))
    discovery = json.loads((EVIDENCE / 'archive_discovery_evidence.json').read_text(encoding='utf-8'))
    recorded = {day: prior.get('berlinDaily', {}).get(day) for day in days}
    report = {'mode': 'fetch' if fetch else 'recorded-evidence',
              'generatedAt': datetime.now(timezone.utc).isoformat(),
              'window': {'start': start, 'end': end, 'timezone': 'Europe/Berlin',
                         'dateBasis': 'source_publication'},
              'inventory': inventory, 'recordedEvidenceDate': prior.get('checked_at'),
              'recordedDaily': recorded,
              'missingRecordedDays': [day for day, count in recorded.items() if count is None],
              'zeroRecordedDays': [day for day, count in recorded.items() if count == 0],
              'recordedEndpointOutcomes': discovery.get('outcomes', []),
              'recordedVerifiedEndpoints': prior.get('verifiedEndpoints', []),
              'limitations': list(prior.get('limitations', [])) + [
                  'Recorded counts are a dated snapshot, not current database or exhaustive news coverage.',
                  'Unpublished dates may reflect editorial rejection; this report measures discovery only.',
                  'Publication timestamps are not event dates; unknown event dates remain unknown.',
                  'This command never ingests, generates, verifies or publishes an edition.'],
              'probes': [], 'articles': [], 'observedDaily': {}, 'errors': []}
    if not fetch:
        return report
    from services.pipeline.ingest import collect_source, publication_day
    from services.pipeline.dedup import deduplicate
    registry = {source['id']: source for source in _registry(registry_path) if isinstance(source, dict) and isinstance(source.get('id'), str)}
    observed, seen = [], set()
    for inspected in inventory['readySources']:
        source = registry[inspected['id']]
        for endpoint in inspected['endpoints']:
            try:
                articles, requests = collect_source(dict(source, feed_url=endpoint, http_cache={}), fixture=False)
                selected = [article for article in articles if start <= publication_day(article) <= end]
                unique = 0
                for article in selected:
                    if article['url'] not in seen:
                        seen.add(article['url'])
                        observed.append(article)
                        unique += 1
                report['probes'].append({'sourceId': source['id'], 'feedUrl': endpoint,
                                         'status': 'success', 'received': len(articles),
                                         'inWindow': len(selected), 'uniqueUrls': unique,
                                         'requests': requests})
            except Exception as error:
                # Do not echo arbitrary transport errors, URLs, HTML or exception bodies.
                detail = str(error).lower()
                reason = ('robots_disallowed' if 'robots' in detail and 'disallow' in detail
                          else 'empty_feed' if 'no usable article' in detail
                          else 'http_or_network_failure' if isinstance(error, OSError)
                          else 'policy_or_feed_validation_failed' if isinstance(error, ValueError)
                          else 'collection_failed')
                report['errors'].append({'sourceId': source['id'], 'feedUrl': endpoint,
                                         'status': 'unavailable', 'error': type(error).__name__,
                                         'reason': reason,
                                         'requests': getattr(error, 'collection_audit', [])})
    report['articles'] = deduplicate(observed)
    report['observedDaily'] = {day: sum(publication_day(article) == day for article in observed) for day in days}
    report['uniqueCanonicalUrls'] = len(observed)
    report['uniqueEvidenceRecords'] = len(report['articles'])
    report['status'] = ('partial' if report['errors'] and report['probes'] else 'unavailable' if report['errors']
                        else 'blocked' if inventory['blockedSources'] else 'complete')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', default=str(ROOT / 'config/sources.yaml'))
    parser.add_argument('--start', default='2026-11-01')
    parser.add_argument('--end', default='2026-11-13')
    parser.add_argument('--fetch', action='store_true', help='Probe reviewed official feeds; no database or AI calls')
    parser.add_argument('--output', help='Optional report path under ignored artifacts/')
    args = parser.parse_args(argv)
    if args.output:
        output = Path(args.output).resolve()
        if not output.is_relative_to((ROOT / 'artifacts').resolve()):
            parser.error('--output must stay inside ignored artifacts/')
    report = probe_archives(args.registry, args.start, args.end, args.fetch)
    if args.output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report['errors'] or report['inventory']['blockedSources'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
