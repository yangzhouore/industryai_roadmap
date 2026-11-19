"""Read canonical evidence in a read-only transaction for local curation."""

import argparse
import json
import os
from pathlib import Path
import sys

from services.review.security import ReviewError, new_file, no_links, private_root
from .manifest import ROOT, TrackerError


def snapshot(dsn):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row,
                         options='-c default_transaction_read_only=on') as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if db.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] != 'on':
            raise TrackerError('Canonical evidence requires a read-only transaction.')
        articles = list(db.execute("""SELECT a.id, a.source_id AS "sourceId", s.name AS publisher,
            a.canonical_url AS url, a.title, a.body_excerpt AS excerpt, a.published_at AS "publishedAt",
            a.event_at AS "eventAt", a.source_timezone AS "sourceTimezone", a.content_hash AS "contentHash"
            FROM raw_articles a JOIN sources s ON s.id=a.source_id
            WHERE a.raw_metadata->'synthetic'='false'::jsonb AND s.source_type<>'fixture'
            ORDER BY a.id"""))
        for article in articles:
            for field in ('publishedAt', 'eventAt'):
                value = article[field]
                article[field] = value.isoformat() if value is not None else None
        editions = list(db.execute("""SELECT id,slug,content FROM issues
            WHERE state='published' AND validated AND content->'synthetic'='false'::jsonb ORDER BY id"""))
        bindings = list(db.execute("""SELECT d.issue_id AS "issueId", d.structured_content->>'id' AS "storyId",
            c.raw_article_id AS "rawArticleId", c.claim_key AS "claimKey", c.source_url AS "sourceUrl"
            FROM digest_stories d JOIN story_citations c ON c.story_id=d.id
            JOIN issues i ON i.id=d.issue_id
            WHERE i.state='published' AND i.validated AND i.content->'synthetic'='false'::jsonb
            AND d.evidence_status='verified'
            AND d.id = i.id || ':' || (d.structured_content->>'id')
            AND EXISTS (SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(i.content->'stories')='array'
                THEN i.content->'stories' ELSE '[]'::jsonb END) AS story(value)
                WHERE story.value=d.structured_content)
            ORDER BY d.issue_id,d.id,c.raw_article_id,c.claim_key"""))
        by_edition = {edition['id']: edition for edition in editions}
        for edition in editions:
            edition['bindings'] = []
        for binding in bindings:
            by_edition[binding.pop('issueId')]['bindings'].append(binding)
        return {'version': 1, 'articles': articles, 'editions': editions}


def private_output(path):
    root = ROOT / 'artifacts'
    target = no_links(Path(path).absolute())
    if not target.is_relative_to(root) or target.parent == root or target == root:
        raise TrackerError('Private output must stay under the checkout artifacts directory.')
    if target.exists():
        raise TrackerError('Private evidence output must be a new file.')
    private_root(target.parent)
    return no_links(target)


def write_json(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    new_file(path, content.encode('utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        dsn = os.environ.get('DATABASE_URL')
        if not dsn:
            raise TrackerError('Set DATABASE_URL for read-only evidence access.')
        output = private_output(args.output)
        data = snapshot(dsn)
        write_json(output, data)
        print(f"Private inventory captured {len(data['articles'])} articles and {len(data['editions'])} editions.")
        return 0
    except (TrackerError, ReviewError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print('Private evidence export failed. Connection and source details were withheld.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
