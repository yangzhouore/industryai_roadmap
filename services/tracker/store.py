"""Import tracker revisions atomically against exact normalized news evidence."""

from datetime import datetime
import json
import os
import subprocess

from .manifest import ISSUE_HASH, ROOT, STAGES, TrackerError


BRIDGE = ROOT / 'packages/shared/public-display-cli.cjs'


def issue_bridge(action, issue):
    payload = json.dumps({'action': action, 'issue': issue}, ensure_ascii=False, allow_nan=False).encode()
    try:
        result = subprocess.run(['node', str(BRIDGE)], input=payload, capture_output=True, timeout=30, check=True,
                                # The fixed data-only bridge has no need for database or provider secrets.
                                env={key: value for key, value in os.environ.items()
                                     if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'PATHEXT'}})
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise TrackerError('The local shared edition gate failed. Check the Node dependency installation.') from exc


def read_issue(db, issue_id, lock=False):
    sql = """SELECT content FROM issues WHERE id=%s AND state='published' AND validated
             AND content->'synthetic'='false'::jsonb"""
    row = db.execute(sql + (' FOR SHARE' if lock else ''), (issue_id,)).fetchone()
    issue = row['content'] if row else None
    if not isinstance(issue, dict) or issue.get('id') != issue_id or not issue_bridge('validate', issue).get('valid'):
        raise TrackerError('A structurally valid, published, non-synthetic edition is required.')
    issue_hash = issue_bridge('hash', issue).get('hash')
    if not isinstance(issue_hash, str) or not ISSUE_HASH.fullmatch(issue_hash):
        raise TrackerError('The existing edition could not be fingerprinted.')
    return issue, issue_hash


def list_editions(db):
    return list(db.execute("""SELECT id, slug, issue_date AS date FROM issues
                            WHERE state='published' AND validated AND content->'synthetic'='false'::jsonb
                            ORDER BY issue_date DESC, id"""))


def list_stories(db, issue_id):
    issue, fingerprint = read_issue(db, issue_id)
    return {'issueId': issue_id, 'issueHash': fingerprint, 'stories': [
        {'storyId': story['id'], 'stage': story['maturity'], 'company': story['company'], 'sourceIds': story['sourceIds']}
        for story in issue['stories']
    ]}


def milestone_history(db, milestone_id):
    rows = list(db.execute("""SELECT r.id,r.revision,r.issue_id,r.issue_hash,r.story_id,r.stage,
        r.withdrawn,r.recorded_at,m.project_id FROM tracker_milestone_revisions r
        JOIN tracker_milestones m ON m.id=r.milestone_id WHERE r.milestone_id=%s ORDER BY r.revision""",
        (milestone_id,)))
    if not rows:
        raise TrackerError('No tracker milestone found for that ID.')
    revisions = []
    for row in rows:
        evidence = db.execute("""SELECT source_key,raw_article_id,kind,published_at,event_at
            FROM tracker_evidence WHERE revision_id=%s ORDER BY source_key""", (row['id'],))
        revisions.append({'revisionId': row['id'], 'revision': row['revision'], 'issueId': row['issue_id'],
                          'issueHash': row['issue_hash'], 'storyId': row['story_id'], 'stage': row['stage'],
                          'withdrawn': row['withdrawn'], 'recordedAt': row['recorded_at'].isoformat(), 'evidence': [
            {'sourceId': source['source_key'], 'rawArticleId': source['raw_article_id'], 'role': source['kind'],
             'publishedAt': source['published_at'].isoformat(),
             'eventAt': source['event_at'].isoformat() if source['event_at'] else None}
            for source in evidence
        ]})
    return {'milestoneId': milestone_id, 'projectId': rows[0]['project_id'], 'revisions': revisions}


def sync_catalog(db, catalog):
    for table, alias_table, foreign, entries in (
        ('tracker_companies', 'tracker_company_aliases', 'company_id', catalog.companies),
        ('tracker_technologies', 'tracker_technology_aliases', 'technology_id', catalog.technologies),
    ):
        for entry in entries:
            db.execute(f'INSERT INTO {table}(id,name_en,name_zh) VALUES(%s,%s,%s) ON CONFLICT(id) DO NOTHING',
                       (entry.id, entry.name_en, entry.name_zh))
            existing = db.execute(f'SELECT name_en,name_zh FROM {table} WHERE id=%s', (entry.id,)).fetchone()
            if existing != {'name_en': entry.name_en, 'name_zh': entry.name_zh}:
                raise TrackerError('Stored tracker catalog names conflict with the reviewed catalog.')
            for key in entry.aliases:
                db.execute(f'INSERT INTO {alias_table}(key,{foreign}) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING',
                           (key, entry.id))
                alias = db.execute(f'SELECT {foreign} FROM {alias_table} WHERE key=%s', (key,)).fetchone()
                if alias[foreign] != entry.id:
                    raise TrackerError('A stored tracker alias belongs to another entity.')


def timestamp(value):
    if value is None:
        return None
    try:
        current = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if current.tzinfo is None:
            raise ValueError
        return current
    except (AttributeError, ValueError) as exc:
        raise TrackerError('Canonical timestamps must include an explicit offset.') from exc


def canonical_evidence(db, issue_id, issue, story, source_roles):
    from psycopg.types.json import Jsonb

    roles = dict(source_roles)
    source_ids = set(story['sourceIds'])
    if not roles.keys() <= source_ids:
        raise TrackerError('Each source role must reference an exact source on the selected story.')
    story_row_id = issue_id + ':' + story['id']
    normalized = db.execute("""SELECT 1 FROM digest_stories
        WHERE id=%s AND issue_id=%s AND evidence_status='verified' AND structured_content=%s""",
        (story_row_id, issue_id, Jsonb(story))).fetchone()
    if normalized is None:
        raise TrackerError('The normalized story must match the exact stored edition story.')
    rows = db.execute("""SELECT a.id AS raw_article_id,a.canonical_url,a.published_at,a.event_at,
        a.source_timezone,s.name AS publisher,sc.source_url
        FROM story_citations sc JOIN raw_articles a ON a.id=sc.raw_article_id
        JOIN sources s ON s.id=a.source_id
        WHERE sc.story_id=%s AND a.raw_metadata->'synthetic'='false'::jsonb AND s.source_type<>'fixture'""",
        (story_row_id,))
    citations = {row['source_url']: row for row in rows if row['source_url'] == row['canonical_url']}
    evidence = []
    for source in sorted((source for source in issue['sources'] if source['id'] in source_ids), key=lambda s: s['id']):
        row = citations.get(source['url'])
        if (not row or source['synthetic'] is not False or source['name'] != row['publisher']
                or timestamp(source['publishedAt']) != row['published_at']
                or timestamp(source['eventAt']) != row['event_at'] or source['timezone'] != row['source_timezone']):
            raise TrackerError('Every story source must match its canonical citation, publisher, and separate dates.')
        evidence.append((source['id'], row['raw_article_id'], roles.get(source['id'], 'other'), row['published_at'],
                         row['event_at'], row['publisher'], row['canonical_url'], row['source_timezone']))
    if len(evidence) != len(source_ids) or len({row[1] for row in evidence}) != len(source_ids):
        raise TrackerError('Each story source requires one distinct canonical article.')
    return evidence


def latest_revision(db, milestone_id):
    return db.execute("""SELECT id,revision,issue_id,issue_hash,story_id,stage,withdrawn
        FROM tracker_milestone_revisions WHERE milestone_id=%s ORDER BY revision DESC LIMIT 1""",
        (milestone_id,)).fetchone()


def duplicate_binding(db, change):
    return db.execute("""SELECT 1 FROM tracker_milestones m
      JOIN tracker_milestone_revisions r ON r.milestone_id=m.id
      WHERE m.project_id=%s AND m.id<>%s AND NOT r.withdrawn
      AND (r.issue_id,r.issue_hash,r.story_id)=(%s,%s,%s) LIMIT 1""",
      (change.project_id, change.milestone_id, change.issue_id, change.issue_hash, change.story_id)).fetchone()


def unchanged_binding(db, head, change, evidence):
    if (head['issue_id'], head['issue_hash'], head['story_id']) != (change.issue_id, change.issue_hash, change.story_id):
        return False
    members = [tuple(row[column] for row in db.execute(
        f'SELECT {column} FROM {table} WHERE revision_id=%s ORDER BY {column}', (head['id'],)))
        for table, column in (('tracker_revision_companies', 'company_id'), ('tracker_revision_technologies', 'technology_id'))]
    previous_evidence = {(row['source_key'], row['kind']) for row in db.execute(
        'SELECT source_key, kind FROM tracker_evidence WHERE revision_id=%s', (head['id'],))}
    return members == [change.companies, change.technologies] and previous_evidence == {(row[0], row[2]) for row in evidence}


def apply_change(db, change, issue_cache):
    if db.execute('SELECT 1 FROM tracker_milestone_revisions WHERE id=%s', (change.revision_id,)).fetchone():
        return 'unchanged'
    head = latest_revision(db, change.milestone_id)
    if (head['revision'] if head else 0) != change.expected_revision:
        raise TrackerError('The milestone head changed; use its current revision before appending a correction.')

    if change.withdraw:
        if head['withdrawn']:
            return 'unchanged'
        issue_id, fingerprint, story_id, stage = (head[key] for key in ('issue_id', 'issue_hash', 'story_id', 'stage'))
        evidence = []
    else:
        if change.issue_id not in issue_cache:
            issue_cache[change.issue_id] = read_issue(db, change.issue_id, lock=True)
        issue, fingerprint = issue_cache[change.issue_id]
        if fingerprint != change.issue_hash:
            raise TrackerError('The stored edition content has changed; compare its current fingerprint.')
        story = next((story for story in issue['stories'] if story['id'] == change.story_id), None)
        if story is None or story['maturity'] not in STAGES or story.get('synthetic', False) is not False:
            raise TrackerError('The selected story must be real and use an existing lifecycle stage.')
        issue_id, story_id, stage = change.issue_id, story['id'], story['maturity']
        evidence = canonical_evidence(db, issue_id, issue, story, change.source_roles)
        if duplicate_binding(db, change):
            raise TrackerError('This exact edition story already anchors another milestone for the same project.')
        if head and not head['withdrawn'] and unchanged_binding(db, head, change, evidence):
            return 'unchanged'

    db.execute('INSERT INTO tracker_projects(id) VALUES(%s) ON CONFLICT(id) DO NOTHING', (change.project_id,))
    db.execute('INSERT INTO tracker_milestones(id,project_id) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING',
               (change.milestone_id, change.project_id))
    db.execute("""INSERT INTO tracker_milestone_revisions(id,milestone_id,revision,issue_id,issue_hash,story_id,stage,withdrawn)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", (change.revision_id, change.milestone_id, change.expected_revision + 1,
                                             issue_id, fingerprint, story_id, stage, change.withdraw))
    for row in evidence:
        db.execute("""INSERT INTO tracker_evidence(revision_id,source_key,raw_article_id,kind,published_at,event_at,
            publisher,canonical_url,source_timezone) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (change.revision_id, *row))
    for company in change.companies:
        db.execute('INSERT INTO tracker_revision_companies(revision_id,company_id) VALUES(%s,%s)',
                   (change.revision_id, company))
    for technology in change.technologies:
        db.execute('INSERT INTO tracker_revision_technologies(revision_id,technology_id) VALUES(%s,%s)',
                   (change.revision_id, technology))
    return 'withdrawn' if change.withdraw else 'appended'


def apply_changes(db, catalog, changes):
    with db.transaction():
        for project in sorted({change.project_id for change in changes}):
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (project,))
        sync_catalog(db, catalog)
        result = []
        issue_cache = {}
        for change in changes:
            status = apply_change(db, change, issue_cache)
            head = latest_revision(db, change.milestone_id)
            result.append({'projectId': change.project_id, 'milestoneId': change.milestone_id,
                           'currentRevision': head['revision'] if head else 0, 'status': status})
        return result
