"""Append-only edition history; callers own validation and replacement transaction."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4


def archive_current_issue(db, issue_id: str, *, review: dict | None = None,
                          expected_content: dict | None = None) -> int:
    """Lock and archive the exact current published issue in the caller's transaction.

    This function never unpublishes, deletes or replaces content. The lead Store
    must archive and replace within one transaction, after replacement validation.
    Rollback restores both current content and history. A stored review is preserved
    verbatim; absent historical review is recorded explicitly rather than invented.
    `review`, when supplied, describes the old content, never its replacement.
    """
    from psycopg.pq import TransactionStatus
    from psycopg.types.json import Jsonb
    if db.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError('Archive requires an explicit publication transaction')
    if not isinstance(issue_id, str) or not issue_id.strip():
        raise ValueError('Issue ID is required')
    db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (issue_id,))
    row = db.execute('SELECT content,state FROM issues WHERE id=%s FOR UPDATE', (issue_id,)).fetchone()
    if not row:
        raise ValueError('Cannot archive a missing issue')
    content = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    if row[1] != 'published':
        raise ValueError('Only an existing published edition can be revised')
    if expected_content is not None and content != expected_content:
        raise ValueError('Current edition changed since revision review')
    issue_hash = sha256(json.dumps({k:v for k,v in content.items() if k not in {'state','validated'}},
        ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if review is None:
        prior = db.execute('''SELECT stats->'review' FROM pipeline_runs
            WHERE stats->>'issueId'=%s AND stats ? 'review'
              AND stats->'review'->>'issueHash'=%s
            ORDER BY started_at DESC, id DESC LIMIT 1''', (issue_id,issue_hash)).fetchone()
        review = prior[0] if prior else {'status':'unavailable','reason':'No persisted historical review receipt'}
    if not isinstance(review, dict):
        raise ValueError('Archived review must be an object')
    if 'issueHash' in review and review['issueHash'] != issue_hash:
        raise ValueError('Historical review does not match the archived edition')
    revision = db.execute('SELECT coalesce(max(revision),0)+1 FROM edition_revisions WHERE issue_id=%s', (issue_id,)).fetchone()[0]
    db.execute('''INSERT INTO edition_revisions(id,issue_id,revision,content,review)
        VALUES(%s,%s,%s,%s,%s)''',
        (str(uuid4()), issue_id, revision, Jsonb(deepcopy(content)), Jsonb(deepcopy(review))))
    return revision
