"""Transactional edition repository; SQLite fixture adapter and PostgreSQL production."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, location='data/digest.sqlite'):
        self.postgres = location.startswith(('postgresql://', 'postgres://'))
        if self.postgres:
            import psycopg
            self.db = psycopg.connect(location, autocommit=True)
        else:
            Path(location).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(location)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS issues (
                  id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, issue_date TEXT UNIQUE NOT NULL,
                  state TEXT NOT NULL, validated BOOLEAN NOT NULL, content TEXT NOT NULL,
                  published_at TEXT);
                CREATE TABLE IF NOT EXISTS collection_records (
                  canonical_url TEXT PRIMARY KEY, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS run_logs (
                  id INTEGER PRIMARY KEY, mode TEXT, status TEXT, stats TEXT, error TEXT);
            ''')

    def execute(self, query, values=()):
        return self.db.execute(query.replace('?', '%s') if self.postgres else query, values)

    def save_draft(self, issue):
        from .verification.schema import Issue
        draft = dict(issue, state='draft', validated=False)
        Issue.model_validate(draft)
        payload = json.dumps(draft, ensure_ascii=False)
        if self.postgres:
            from psycopg.types.json import Jsonb
            payload = Jsonb(draft)
        with self.db.transaction() if self.postgres else self.db:
            self.execute('''INSERT INTO issues(id,slug,issue_date,state,validated,content)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content
                WHERE issues.state='draft' ''',
                (draft['id'],draft['slug'],draft['date'],'draft',False,payload))

    def publish(self, issue, review=None):
        from .verification import validate_issue
        draft = dict(issue, state='draft', validated=False)
        errors = validate_issue(draft, review=review) if review is not None else validate_issue(draft)
        if errors:
            raise ValueError('; '.join(errors))
        published = dict(draft, state='published', validated=True)
        if not self.postgres:
            self.db.execute('BEGIN IMMEDIATE')
        with self.db.transaction() if self.postgres else self.db:
            if self.postgres:
                self.execute('SELECT pg_advisory_xact_lock(hashtext(?))', (issue['id'],))
            existing = self.execute('SELECT content FROM issues WHERE id=?', (issue['id'],)).fetchone()
            if existing:
                old = existing[0] if isinstance(existing[0], dict) else json.loads(existing[0])
                if old['slug'] != issue['slug'] or old['date'] != issue['date']:
                    raise ValueError('Edition identity cannot change')
                if old == published:
                    return False
                if old.get('state') == 'published':
                    raise ValueError('Published editions are immutable; create a correction edition')
            query = '''INSERT INTO issues(id,slug,issue_date,state,validated,content,published_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                state=excluded.state,validated=excluded.validated,content=excluded.content,
                published_at=excluded.published_at'''
            content = json.dumps(draft, ensure_ascii=False)
            if self.postgres:
                from psycopg.types.json import Jsonb
                content = Jsonb(draft)
            self.execute(query, (draft['id'], draft['slug'], draft['date'], 'draft', False, content, None))
            validated = dict(draft, state='validated', validated=True)
            for state, data in [('validated', validated), ('published', published)]:
                errors = validate_issue(data, review=review) if review is not None else validate_issue(data)
                if errors:
                    raise ValueError('; '.join(errors))
                payload = json.dumps(data, ensure_ascii=False)
                if self.postgres:
                    payload = Jsonb(data)
                self.execute('UPDATE issues SET state=?,validated=?,content=?,published_at=? WHERE id=?',
                             (state, True, payload, datetime.now(timezone.utc).isoformat() if state == 'published' else None, issue['id']))
            if self.postgres:
                self._persist_evidence(issue, review)
            if review is not None:
                self.log_run('live','verified',{'issueId':issue['id'],'review':review})
        return True

    def _persist_evidence(self, issue, review=None):
        from hashlib import sha256
        from urllib.parse import urlsplit
        from psycopg.types.json import Jsonb
        for source in issue['sources']:
            old = self.execute('SELECT raw_metadata FROM raw_articles WHERE canonical_url=?', (source['url'],)).fetchone()
            if old:
                evidence = old[0]
                old_excerpt = evidence.get('excerpt')
                if isinstance(old_excerpt, dict):
                    excerpt_matches = old_excerpt == source['excerpt']
                else:
                    original_locale = (evidence.get('language') or 'en').replace('_','-').split('-')[0].lower()
                    excerpt_matches = source['excerpt'].get(original_locale) in {
                        old_excerpt, evidence.get('title','') + '\n' + (old_excerpt or '')}
                def timestamp(value):
                    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None
                if (not excerpt_matches or timestamp(evidence.get('publishedAt')) != timestamp(source['publishedAt'])
                        or timestamp(evidence.get('eventAt')) != timestamp(source['eventAt'])
                        or evidence.get('timezone') != source['timezone']
                        or evidence.get('synthetic') != source['synthetic']):
                    raise ValueError('Canonical source evidence is immutable; use a versioned source URL')
            self.execute('''INSERT INTO sources(id,name,homepage,source_type,fetch_policy)
                VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
                (source['id'],source['name'],'https://'+urlsplit(source['url']).netloc,
                 'fixture' if source['synthetic'] else 'reviewed',Jsonb({'fetch':False})))
            self.execute('''INSERT INTO raw_articles(id,source_id,canonical_url,title,body_excerpt,
                published_at,event_at,source_timezone,content_hash,raw_metadata)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(canonical_url) DO NOTHING''',
                (source['id'],source['id'],source['url'],source['name'],source['excerpt']['en'],
                 source['publishedAt'],source['eventAt'],source['timezone'],
                 sha256(json.dumps(source['excerpt'],sort_keys=True).encode()).hexdigest(),Jsonb(source)))
        for position, story in enumerate(issue['stories']):
            story_id = issue['id'] + ':' + story['id']
            self.execute('''INSERT INTO story_clusters(id,label,event_date,category,maturity,status)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
                (story_id,story['title']['en'],issue['date'],story['category'],story['maturity'],'published'))
            self.execute('''INSERT INTO digest_stories(id,issue_id,cluster_id,position,kind,structured_content,evidence_status)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
                (story_id,issue['id'],story_id,position,story['kind'],Jsonb(story),story['evidenceStatus']))
            from .scoring import score_story
            trace = score_story(story)
            classified = next((c for c in (review or {}).get('classifications',[]) if c.get('articleId') in story['sourceIds']),None)
            if classified and isinstance(classified.get('scoreTrace'),dict):
                trace = classified['scoreTrace']
            self.execute('''INSERT INTO scores(cluster_id,scoring_version,dimensions_json,final_score)
                VALUES(?,?,?,?) ON CONFLICT DO NOTHING''',
                (story_id,trace['version'],Jsonb(trace),trace['finalScore']))
            canonical_company = ' '.join(story['company'].casefold().split())
            entity_id = 'entity-' + sha256(canonical_company.encode()).hexdigest()[:24]
            self.execute('''INSERT INTO entities(id,name,entity_type,canonical_name)
                VALUES(?,?,?,?) ON CONFLICT DO NOTHING''',
                (entity_id,story['company'],'organization',canonical_company))
            self.execute('''INSERT INTO story_entity_links(cluster_id,entity_id,relationship)
                VALUES(?,?,?) ON CONFLICT DO NOTHING''', (story_id,entity_id,'subject'))
            for entity in (classified or {}).get('entities',[]):
                canonical = ' '.join(entity['name'].casefold().split())
                eid = 'entity-' + sha256(canonical.encode()).hexdigest()[:24]
                self.execute('INSERT INTO entities(id,name,entity_type,canonical_name) VALUES(?,?,?,?) ON CONFLICT DO NOTHING',
                             (eid,entity['name'],entity['type'],canonical))
                self.execute('INSERT INTO story_entity_links(cluster_id,entity_id,relationship) VALUES(?,?,?) ON CONFLICT DO NOTHING',(story_id,eid,'mentioned'))
            for source_id in story['sourceIds']:
                source = next(s for s in issue['sources'] if s['id'] == source_id)
                article_id = self.execute('SELECT id FROM raw_articles WHERE canonical_url=?',(source['url'],)).fetchone()[0]
                self.execute('''INSERT INTO story_citations(story_id,raw_article_id,claim_key,source_url,excerpt_or_pointer)
                    VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING''',
                    (story_id,article_id,'summary',source['url'],json.dumps(source['excerpt'],ensure_ascii=False)))
                self.execute('INSERT INTO article_cluster_links(cluster_id,article_id) VALUES(?,?) ON CONFLICT DO NOTHING', (story_id,article_id))
            for locale in ('en','zh'):
                self.execute('''INSERT INTO translations(story_id,locale,title,summary,structured_body,validation_state)
                    VALUES(?,?,?,?,?,?) ON CONFLICT DO NOTHING''',
                    (story_id,locale,story['title'][locale],story['summary'][locale],
                     Jsonb({'why':story['why'][locale],'limitation':story['limitation'][locale]}),'validated'))

    def log_run(self, mode, status, stats=None, error=None):
        with self.db.transaction() if self.postgres else self.db:
            if self.postgres:
                from psycopg.types.json import Jsonb
                self.execute('''INSERT INTO pipeline_runs(id,ended_at,mode,status,stage,stats,error)
                    VALUES(?,?,?,?,?,?,?)''', (str(uuid.uuid4()),datetime.now(timezone.utc),mode,status,'publication',Jsonb(stats or {}),error))
            else:
                self.execute('INSERT INTO run_logs(mode,status,stats,error) VALUES(?,?,?,?)',
                             (mode,status,json.dumps(stats or {}),error))

    def published(self):
        rows = self.execute("SELECT content FROM issues WHERE state='published' AND validated=? ORDER BY issue_date DESC", (True,)).fetchall()
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]

    def close(self):
        self.db.close()
