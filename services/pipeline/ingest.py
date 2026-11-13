"""Offline and opt-in feed ingestion with persistent audit and candidate clusters."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo
from .collectors import FeedClient, canonicalize_url
from .dedup import cluster_events, deduplicate, normalize_title
from .extraction import parse_feed

FIXTURES = Path(__file__).parent / 'collectors' / 'fixtures'
ROOT = Path(__file__).resolve().parents[2]

def load_registry(path, *, fixture=False):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('sources'), list):
        raise ValueError('Registry requires sources array (JSON-compatible YAML)')
    seen, sources = set(), []
    for source in data['sources']:
        if not isinstance(source, dict) or not isinstance(source.get('id'), str) or not source['id']:
            raise ValueError('Every registry source needs an ID')
        if source['id'] in seen:
            raise ValueError('Duplicate registry source ID')
        seen.add(source['id'])
        if source.get('active') is not True:
            continue
        for key in ('name', 'homepage', 'feed_url'):
            if not isinstance(source.get(key), str) or not source[key].strip():
                raise ValueError(f"Missing {key}")
        feed, home = canonicalize_url(source['feed_url']), canonicalize_url(source['homepage'])
        hosts = source.get('allowed_hosts')
        if not isinstance(hosts, list) or not hosts or not all(isinstance(h, str) for h in hosts):
            raise ValueError('Source requires explicit allowed_hosts')
        if urlsplit(feed).scheme != 'https' or urlsplit(home).scheme != 'https' or urlsplit(feed).hostname not in hosts:
            raise ValueError('Feed must use HTTPS and an approved host')
        if any(source.get(key) is not True for key in ('feed_permitted','policy_reviewed','excerpt_permitted')):
            raise ValueError('Active source requires reviewed feed and excerpt permissions')
        if source.get('synthetic') is not fixture:
            raise ValueError('Fixture and real source registries cannot be mixed')
        host = urlsplit(feed).hostname
        if not fixture and (host in {'example.org','example.com','example.net'} or host.endswith(('.example.org','.example.com','.example.net'))):
            raise ValueError('Live source cannot use reserved example domains')
        if not fixture and (not source.get('policy_evidence') or not source.get('policy_checked_at')):
            raise ValueError('Live source requires dated policy evidence')
        item = dict(source, feed_url=feed, homepage=home)
        if fixture:
            candidate = (path.parent / source.get('fixture_file', '')).resolve()
            if not candidate.is_relative_to(path.parent) or not candidate.is_file():
                raise ValueError('Fixture file must stay within registry directory')
            item['fixture_path'] = candidate
        sources.append(item)
    return sources

class ArticleStore:
    def __init__(self, database):
        self.postgres = str(database).startswith(('postgres://','postgresql://'))
        if self.postgres:
            import psycopg
            self.db = psycopg.connect(database, autocommit=True)
        else:
            Path(database).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(database, isolation_level=None)
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.executescript('''
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,name TEXT NOT NULL,homepage TEXT NOT NULL,feed_url TEXT,source_type TEXT NOT NULL,active BOOLEAN NOT NULL,fetch_policy TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS raw_articles(id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id),canonical_url TEXT UNIQUE NOT NULL,title TEXT NOT NULL,body_excerpt TEXT NOT NULL,published_at TEXT NOT NULL,event_at TEXT,source_timezone TEXT NOT NULL,collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,content_hash TEXT NOT NULL,raw_metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS story_clusters(id TEXT PRIMARY KEY,label TEXT NOT NULL,event_date TEXT,category TEXT NOT NULL,maturity TEXT NOT NULL,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS article_cluster_links(cluster_id TEXT NOT NULL REFERENCES story_clusters(id),article_id TEXT NOT NULL REFERENCES raw_articles(id),PRIMARY KEY(cluster_id,article_id));
CREATE TABLE IF NOT EXISTS pipeline_runs(id TEXT PRIMARY KEY,started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,ended_at TEXT,mode TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,stats TEXT NOT NULL,error TEXT);
''')
    def execute(self, sql, args=()):
        return self.db.execute(sql.replace('?', '%s') if self.postgres else sql, args)
    def json_value(self, value):
        if self.postgres:
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        return json.dumps(value, ensure_ascii=False, default=str)
    @contextmanager
    def transaction(self):
        if self.postgres:
            with self.db.transaction():
                yield
        else:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
    def start_run(self, mode):
        run_id = uuid4().hex
        self.execute('INSERT INTO pipeline_runs(id,mode,status,stage,stats) VALUES(?,?,?,?,?)',(run_id,mode,'running','collection',self.json_value({})))
        return run_id
    def finish_run(self, run_id, stats, errors):
        status = 'partial' if errors and stats['sourcesSucceeded'] else 'failed' if errors else 'success'
        self.execute('UPDATE pipeline_runs SET ended_at=?,status=?,stats=?,error=? WHERE id=?',(datetime.now(timezone.utc).isoformat(),status,self.json_value(stats),json.dumps(errors) if errors else None,run_id))
    def source_cache(self, source):
        row = self.execute('SELECT feed_url,fetch_policy FROM sources WHERE id=?',(source['id'],)).fetchone()
        if not row or row[0] != source['feed_url']:
            return {}
        policy = row[1] if isinstance(row[1],dict) else json.loads(row[1])
        return policy.get('http_cache',{})
    def persist_source(self, source, articles):
        added = 0
        with self.transaction():
            policy = {k:v for k,v in source.items() if k not in {'fixture_path','name','id'}}
            self.execute('''INSERT INTO sources(id,name,homepage,feed_url,source_type,active,fetch_policy) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,homepage=excluded.homepage,feed_url=excluded.feed_url,active=excluded.active,fetch_policy=excluded.fetch_policy''',(source['id'],source['name'],source['homepage'],source['feed_url'],'fixture' if source['synthetic'] else 'rss',True,self.json_value(policy)))
            for article in articles:
                article_id = sha256(article['url'].encode()).hexdigest()
                metadata = dict(article)
                cursor = self.execute('''INSERT INTO raw_articles(id,source_id,canonical_url,title,body_excerpt,published_at,event_at,source_timezone,content_hash,raw_metadata) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(canonical_url) DO NOTHING''',(article_id,source['id'],article['url'],article['title'],article['excerpt'],article['publishedAt'],article.get('eventAt'),article['timezone'],article['contentHash'],self.json_value(metadata)))
                added += cursor.rowcount
            for group in cluster_events(articles).values():
                first = group[0]
                grouping_day = (first.get('eventAt') or first['publishedAt'])[:10]
                event_date = first['eventAt'][:10] if first.get('eventAt') else None
                cluster_id = sha256((grouping_day+':'+normalize_title(first['title'])).encode()).hexdigest()
                self.execute('''INSERT INTO story_clusters(id,label,event_date,category,maturity,status) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',(cluster_id,first['title'],event_date,'unclassified','unknown','candidate'))
                for article in group:
                    article_id = self.execute('SELECT id FROM raw_articles WHERE canonical_url=?',(article['url'],)).fetchone()[0]
                    self.execute('INSERT INTO article_cluster_links(cluster_id,article_id) VALUES(?,?) ON CONFLICT DO NOTHING',(cluster_id,article_id))
        return added
    def close(self):
        self.db.close()

def collect_source(source, fixture):
    client = None
    try:
        if fixture:
            payload = source['fixture_path'].read_bytes()
        else:
            client = FeedClient(source['allowed_hosts'],interval=source.get('request_interval_seconds',1.0))
            previous = source.get('http_cache',{})
            payload = client.fetch(source['feed_url'], feed_permitted=True,validators=previous)
            source['http_cache'] = {**previous, **{k:v for k,v in client.response_metadata.items() if v is not None}}
            if client.not_modified:
                return [],client.audit
        articles = parse_feed(payload, source['id'], source['name'])
        if not articles:
            raise ValueError('Feed contained no usable article records')
    except Exception as error:
        error.collection_audit = client.audit if client else []
        raise
    fetched_at = datetime.now(timezone.utc).isoformat()
    for article in articles:
        article['url'] = canonicalize_url(article['url'])
        parts = urlsplit(article['url'])
        if parts.scheme != 'https' or parts.hostname not in source['allowed_hosts']:
            raise ValueError('Article URL is outside approved source hosts')
        if not article['publishedAt']:
            raise ValueError('Article requires an auditable publication timestamp')
        if fixture and not (parts.hostname == 'example.org' and parts.path.startswith('/fixtures/')):
            raise ValueError('Synthetic article must use reserved fixture namespace')
        article['synthetic'] = fixture
        article['fetchedAt'] = fetched_at
        article['feedUrl'] = source['feed_url']
        article['sourceType'] = 'fixture' if fixture else 'rss'
        article['attribution'] = source['name']
        article['policyEvidence'] = source.get('policy_evidence',[])
    return deduplicate(articles), client.audit if client else [{'url':source['feed_url'],'status':'offline-fixture'}]

def ingest(registry=None, database='data/digest.sqlite', mode='fixture'):
    if mode not in {'fixture','live'}:
        raise ValueError('Collection mode must be fixture or live')
    registry = Path(registry) if registry else FIXTURES/'registry.json' if mode == 'fixture' else ROOT/'config/sources.yaml'
    store = ArticleStore(database)
    stats = {'sourcesSucceeded':0,'sourcesFailed':0,'articlesSeen':0,'articlesInserted':0,'notModified':0,'audit':[]}
    errors, run_id = [], None
    try:
        run_id = store.start_run(mode)
        sources = load_registry(registry, fixture=mode == 'fixture')
        for source in sources:
            try:
                if mode == 'live':
                    source['http_cache'] = store.source_cache(source)
                articles,audit = collect_source(source,fixture=mode == 'fixture')
                inserted = store.persist_source(source,articles)
                stats['sourcesSucceeded'] += 1
                stats['articlesSeen'] += len(articles)
                stats['articlesInserted'] += inserted
                stats['notModified'] += int(any(request.get('status') == 304 for request in audit))
                stats['audit'].append({'sourceId':source['id'],'articles':len(articles),'inserted':inserted,'requests':audit})
            except Exception as error:
                stats['sourcesFailed'] += 1
                errors.append({'sourceId':source['id'],'feedUrl':source['feed_url'],'error':str(error),'requests':getattr(error,'collection_audit',[])})
        store.finish_run(run_id,stats,errors)
        return {'mode':mode,'runId':run_id,**stats,'errors':errors}
    except Exception as error:
        errors.append({'stage':'registry','error':str(error)})
        if run_id:
            store.finish_run(run_id,stats,errors)
        raise
    finally:
        store.close()


def publication_day(article, timezone_name='Europe/Berlin'):
    """A digest day follows publication time; never infer the event date from it."""
    timestamp = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('Publication time requires an explicit timezone')
    return timestamp.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def backfill(registry, database, start, end, timezone_name='Europe/Berlin'):
    """Collect explicitly reviewed historical feed endpoints for an inclusive date range.

    Coverage is bounded by publisher-accessible feeds, not an assertion of complete
    worldwide news coverage. Raw rows outside the requested window are not imported.
    """
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or (last-first).days > 62:
        raise ValueError('Backfill window must be ordered and at most 63 days')
    ZoneInfo(timezone_name)
    start, end = first.isoformat(), last.isoformat()
    store = ArticleStore(database)
    stats = {'sourcesSucceeded':0,'sourcesFailed':0,'articlesSeen':0,'articlesInserted':0,
             'window':{'start':start,'end':end,'timezone':timezone_name,'dateBasis':'source_publication'},
             'coverage':{(first+timedelta(days=i)).isoformat():0 for i in range((last-first).days+1)},
             'audit':[]}
    errors, run_id = [], None
    coverage_urls = {day:set() for day in stats['coverage']}
    try:
        run_id = store.start_run('backfill')
        store.execute('UPDATE pipeline_runs SET stage=? WHERE id=?',('collection_backfill',run_id))
        for source in load_registry(registry):
            source['http_cache'] = store.source_cache(source)
            endpoints = list(dict.fromkeys([source['feed_url'], *source.get('archive_feeds',[])]))
            source_success = False
            for endpoint in endpoints:
                try:
                    canonical = canonicalize_url(endpoint)
                    parts = urlsplit(canonical)
                    if parts.scheme != 'https' or parts.hostname not in source['allowed_hosts']:
                        raise ValueError('Historical feed URL is outside reviewed source hosts')
                    request_source = dict(source, feed_url=canonical, http_cache={})
                    records, requests = collect_source(request_source, fixture=False)
                    selected = [record for record in records if start <= publication_day(record,timezone_name) <= end]
                    for record in selected:
                        record['backfillWindow'] = dict(stats['window'])
                        record['publicationDay'] = publication_day(record,timezone_name)
                        record['eventDateBasis'] = 'not_inferred_from_publication'
                    inserted = store.persist_source(source,selected)
                    stats['articlesSeen'] += len(selected)
                    stats['articlesInserted'] += inserted
                    for record in selected:
                        coverage_urls[record['publicationDay']].add(record['url'])
                        stats['coverage'][record['publicationDay']] = len(coverage_urls[record['publicationDay']])
                    stats['audit'].append({'sourceId':source['id'],'feedUrl':canonical,
                                           'received':len(records),'inWindow':len(selected),
                                           'inserted':inserted,'requests':requests})
                    source_success = True
                except Exception as error:
                    errors.append({'sourceId':source['id'],'feedUrl':endpoint,'error':str(error),
                                   'requests':getattr(error,'collection_audit',[])})
            stats['sourcesSucceeded' if source_success else 'sourcesFailed'] += 1
        store.finish_run(run_id,stats,errors)
        return {'mode':'backfill','runId':run_id,**stats,'errors':errors}
    except Exception as error:
        errors.append({'stage':'backfill','error':str(error)})
        if run_id:
            store.finish_run(run_id,stats,errors)
        raise
    finally:
        store.close()

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['fixture','live','backfill'],default='fixture')
    parser.add_argument('--registry')
    parser.add_argument('--database',default='data/digest.sqlite')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--timezone',default='Europe/Berlin')
    args = parser.parse_args(argv)
    if args.mode in {'live','backfill'} and not args.registry:
        parser.error('Live collection requires an explicitly supplied reviewed registry')
    if args.mode == 'backfill':
        if not args.start or not args.end:
            parser.error('Backfill requires --start and --end inclusive publication dates')
        result = backfill(args.registry,args.database,args.start,args.end,args.timezone)
    else:
        result = ingest(args.registry,args.database,args.mode)
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result['errors'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
