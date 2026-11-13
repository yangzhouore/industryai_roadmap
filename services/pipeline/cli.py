"""Offline-first command entrypoint. No network or API keys in fixture mode."""
import argparse
import json
import os
from pathlib import Path
from .store import Store

ROOT = Path(__file__).resolve().parents[2]


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['fixture', 'dry-run', 'live'], default='fixture')
    parser.add_argument('--input', default=str(ROOT / 'packages/shared/fixtures/issues.json'))
    parser.add_argument('--database', default=None)
    args = parser.parse_args(argv)
    from .collectors import collect_fixture, canonicalize_url
    from .editorial import prepare_issue
    from .verification import validate_issue
    if args.mode == 'live' and not os.getenv('DATABASE_URL'):
        parser.error('Live publication requires DATABASE_URL and reviewed, sourced input')
    store = None if args.mode == 'dry-run' else Store(args.database or (os.environ['DATABASE_URL'] if args.mode == 'live' else 'data/digest.sqlite'))
    stats = {'issues': 0, 'sources': 0, 'published': 0, 'unchanged': 0}
    try:
        issues = json.loads(Path(args.input).read_text(encoding='utf-8'))
        if not isinstance(issues, list) or not issues:
            raise ValueError('Input must be a nonempty array of editions')
        if args.mode == 'live' and any(i.get('synthetic') for i in issues):
            raise ValueError('Synthetic editions cannot be published in live mode')
        for issue in issues:
            errors = validate_issue(issue)
            if errors:
                raise ValueError('; '.join(errors))
            for source in issue['sources']:
                source['url'] = canonicalize_url(source['url'])
        records = collect_fixture(issues) if all(i['synthetic'] for i in issues) else [dict(s, url=canonicalize_url(s['url'])) for i in issues for s in i['sources']]
        if args.mode == 'fixture' and not all(i['synthetic'] for i in issues):
            raise ValueError('Fixture mode requires synthetic editions')
        drafts = [prepare_issue(issue) for issue in issues]
        stats.update(issues=len(issues), sources=len(records))
        if args.mode == 'dry-run':
            print(json.dumps(dict(mode=args.mode, **stats)))
            return stats
        for issue in drafts:
            changed = store.publish(issue)
            stats['published' if changed else 'unchanged'] += 1
        if not store.postgres:
            with store.db:
                for record in records:
                    url = record.get('canonical_url') or record.get('canonicalUrl') or record['url']
                    store.execute('INSERT INTO collection_records VALUES(?,?) ON CONFLICT(canonical_url) DO NOTHING', (url, json.dumps(record, ensure_ascii=False)))
        store.log_run(args.mode, 'success', stats)
        print(json.dumps(dict(mode=args.mode, **stats)))
        return stats
    except Exception as exc:
        if store:
            store.log_run(args.mode, 'failed', stats, str(exc))
        raise
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    run()
