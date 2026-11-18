"""Default-deny HTTP/RSC checks over an isolated, deliberately tainted database.

Mock editorial receipts establish validation only, never human display clearance.
"""
from copy import deepcopy
from contextlib import contextmanager
import html
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATE = '2024-04-15'
HIDDEN_DATES = ('2026-11-10', '2026-11-11', '2026-11-12', '2024-04-16', '2024-04-17', '2024-04-18', '2024-04-19')
WITHHELD_DATES = (PUBLIC_DATE, *HIDDEN_DATES)
SENTINELS = ('QA_PRIVATE_ISSUE_EVIDENCE', 'QA_PRIVATE_STORY_EVIDENCE',
             'QA_PRIVATE_SOURCE_EVIDENCE', 'QA_COPIED_EDITORIAL_EN',
             'QA_COPIED_EDITORIAL_ZH', 'QA_SOURCEONLYTOKEN_EXCERPT_EN',
             'QA_SOURCEONLYTOKEN_EXCERPT_ZH', 'QA_PRIVATE_ASSET',
             'QA_PRIVATE_RESPONSE', 'QA_PRIVATE_REVIEW')
TRACKER_PRIVATE_PROJECT = 'project-' + 'a' * 24
TRACKER_PRIVATE_MILESTONE = 'milestone-' + 'b' * 24


def seed_uncleared_tracker(store, issue):
    from services.tracker.store import issue_bridge

    story = issue['stories'][0]
    fingerprint = issue_bridge('hash', issue)['hash']
    revision = 'revision-' + 'c' * 64
    with store.db.transaction():
        store.db.execute('INSERT INTO tracker_projects(id) VALUES (%s)', (TRACKER_PRIVATE_PROJECT,))
        store.db.execute('INSERT INTO tracker_milestones(id,project_id) VALUES (%s,%s)',
                         (TRACKER_PRIVATE_MILESTONE, TRACKER_PRIVATE_PROJECT))
        store.db.execute('''INSERT INTO tracker_milestone_revisions
            (id,milestone_id,revision,issue_id,issue_hash,story_id,stage) VALUES (%s,%s,1,%s,%s,%s,%s)''',
            (revision, TRACKER_PRIVATE_MILESTONE, issue['id'], fingerprint, story['id'], story['maturity']))
        for source in (item for item in issue['sources'] if item['id'] in story['sourceIds']):
            article = store.db.execute('SELECT id FROM raw_articles WHERE canonical_url=%s', (source['url'],)).fetchone()
            assert article is not None, 'Tracker evidence must reuse the normalized source URL'
            store.db.execute('''INSERT INTO tracker_evidence
                (revision_id,source_key,raw_article_id,kind,published_at,event_at,publisher,canonical_url,source_timezone)
                VALUES (%s,%s,%s,'other',%s,%s,%s,%s,%s)''',
                (revision, source['id'], article[0], source['publishedAt'], source['eventAt'],
                 source['name'], source['url'], source['timezone']))


def taint(issue):
    """Keep a valid stored shape while marking every prose/private field family."""
    issue = deepcopy(issue)
    copied = {'en': SENTINELS[3], 'zh': SENTINELS[4]}
    issue.update(title=deepcopy(copied), introduction=deepcopy(copied),
                 evidence={'raw': SENTINELS[0]}, assets=[SENTINELS[7]],
                 modelResponse=SENTINELS[8], review={'private': SENTINELS[9]})
    for story in issue['stories']:
        for field in ('title', 'summary', 'why', 'limitation'):
            story[field] = deepcopy(copied)
        story.update(evidence={'raw': SENTINELS[1]}, images=[SENTINELS[7]],
                     modelResponse=SENTINELS[8], review=SENTINELS[9])
    for source in issue['sources']:
        source.update(excerpt={'en': SENTINELS[5], 'zh': SENTINELS[6]},
                      evidence={'raw': SENTINELS[2]}, rawArticle=SENTINELS[2],
                      assets=[SENTINELS[7]], modelResponse=SENTINELS[8])
    return issue


def assert_no_leak(body):
    # Includes HTML metadata, inline hydration JSON, feeds and raw RSC payloads.
    body = html.unescape(body)
    assert not any(marker in body for marker in SENTINELS), 'Private evidence/editorial leaked'
    assert 'example.org/fixtures/' not in body and 'fixture-notice' not in body
    assert all('/digest/'+day not in body for day in WITHHELD_DATES)
    assert 'nist.gov/programs-projects/digital-twins-advanced-manufacturing' not in body


def test_database_url(value, isolated=False):
    parts = urlsplit(value)
    # libpq query parameters can override the parsed authority/database. The
    # disposable target must mean exactly what the URL guard inspected.
    if parts.query or parts.fragment:
        raise ValueError('Database smoke setup rejects query/fragment connection overrides')
    local = parts.hostname in {'localhost', '127.0.0.1', '::1'}
    named_test = parts.path.rsplit('/', 1)[-1].endswith('_test')
    github_disposable = os.getenv('CI') == 'true' and os.getenv('GITHUB_ACTIONS') == 'true' and local
    if not isolated or parts.scheme not in {'postgres', 'postgresql'} or not (named_test or github_disposable):
        raise ValueError('Database smoke setup requires an explicitly isolated TEST_DATABASE_URL')
    return parts


@contextmanager
def isolated_projection(database, *, isolated=False):
    """Create/drop only one owned random schema in an explicitly disposable DB."""
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from services.pipeline.editorial.live import generate_real_issue
    from services.pipeline.editorial import prepare_issue
    from services.pipeline.editorial.test_live import ARTICLE, ScriptedHTTP, provider
    from services.pipeline.store import Store
    parts = test_database_url(database, isolated)
    schema = 'web_smoke_' + uuid4().hex
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in {'options', 'schema'}]
    sql_url = urlunsplit(parts._replace(query=urlencode(query+[('options', '-c search_path='+schema+',public')], quote_via=quote)))
    web_url = urlunsplit(parts._replace(query=urlencode(query+[('schema', schema)], quote_via=quote)))
    admin = psycopg.connect(database, autocommit=True)
    store = None
    created = False
    try:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        created = True
        store = Store(sql_url)
        for migration in sorted((ROOT/'packages/db/prisma/migrations').glob('*/migration.sql')):
            store.db.execute(migration.read_text(encoding='utf-8'), prepare=False)
        for issue in json.loads((ROOT/'packages/shared/fixtures/issues.json').read_text(encoding='utf-8')):
            store.publish(prepare_issue(issue))
        draft, review = generate_real_issue([deepcopy(ARTICLE)], PUBLIC_DATE, provider(ScriptedHTTP()))
        store.publish(draft, review)
        for day, state, validated in (('2024-04-16', 'draft', False), ('2024-04-17', 'validated', True)):
            private = dict(deepcopy(draft), id='qa-private-'+day, date=day, slug=day, state=state, validated=validated)
            store.execute('INSERT INTO issues(id,slug,issue_date,state,validated,content) VALUES(?,?,?,?,?,?)',
                          (private['id'], day, day, state, validated, Jsonb(private)))
        malformed = dict(deepcopy(draft), id='qa-malformed', date='2024-04-18', slug='2024-04-18',
                         state='published', validated=True, title={'en': '', 'zh': ''})
        store.execute('''INSERT INTO issues(id,slug,issue_date,state,validated,content,published_at)
            VALUES(?,?,?,?,?,?,now())''', ('qa-malformed', '2024-04-18', '2024-04-18',
                                          'published', True, Jsonb(malformed)))
        # A malformed JSON projection must be rejected even if SQL publication flags pass.
        invalid = dict(deepcopy(draft), id='qa-invalid', date='2024-04-19', slug='2024-04-19',
                       state='published', validated=True, title={'en': 'Incomplete'})
        store.execute('INSERT INTO issues(id,slug,issue_date,state,validated,content,published_at) VALUES(?,?,?,?,?,?,now())',
                      (invalid['id'], invalid['slug'], invalid['date'], 'published', True, Jsonb(invalid)))
        # SQL-only edits stay in this disposable schema. Never grant policy approvals.
        for row in store.execute('SELECT id,content FROM issues').fetchall():
            updated = taint(row[1])
            store.execute('UPDATE issues SET content=? WHERE id=?', (Jsonb(updated), row[0]))
            if row[0] == draft['id']:
                seed_uncleared_tracker(store, updated)
        yield web_url
    finally:
        if store:
            store.close()
        if created:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()


def check(base):
    checked = 0
    for locale in ('en', 'zh'):
        routes = ('', '/archive', '/search', '/search?q=NIST', '/search?q=SOURCEONLYTOKEN',
                  '/search?q=COPIED_EDITORIAL', '/search?q=NIST&category=Manufacturing%20AI',
                  '/search?q=SOURCEONLYTOKEN&page=2', '/search?category=Manufacturing%20AI',
                  '/methodology', '/privacy', '/whatsnew')
        for route in routes:
            for rsc in (False, True):
                request = Request(base+'/'+locale+route, headers={'Rsc': '1'} if rsc else {})
                with urlopen(request, timeout=30) as response:
                    body = html.unescape(response.read().decode())
                    assert response.status == 200, route
                    assert_no_leak(body)
                    if rsc:
                        assert 'text/x-component' in response.headers.get('Content-Type', '')
                    else:
                        assert f'lang="{locale}"' in body, route
                        if route in ('', '/archive') or route.startswith('/search'):
                            assert ('No published news yet.' if locale == 'en' else '\u6682\u65e0\u5df2\u53d1\u5e03\u65b0\u95fb\u3002') in body
                        if route.startswith('/search'):
                            assert 'class="search-result"' not in body
                            options = re.findall(r'<option\b([^>]*)>(.*?)</option>', body)
                            assert len(options) == 1 and 'value=""' in options[0][0], route
                checked += 1
        for day in (*WITHHELD_DATES, 'not-a-real-issue'):
            for suffix in ('', '/sources'):
                for rsc in (False, True):
                    request = Request(base+'/'+locale+'/digest/'+day+suffix,
                                      headers={'Rsc': '1'} if rsc else {})
                    try:
                        with urlopen(request, timeout=30) as response:
                            body = response.read().decode()
                            assert rsc and 'NEXT_HTTP_ERROR_FALLBACK;404' in body, day
                    except HTTPError as error:
                        assert error.code == 404
                        body = error.read().decode()
                    # A 404 RSC request can echo the requested path; it cannot carry prose.
                    assert_no_leak(body.replace('/digest/'+day, '/withheld-route'))
                    checked += 1
        with urlopen(base+'/'+locale+'/rss.xml', timeout=30) as response:
            assert 'no-store' in response.headers.get('Cache-Control', '')
            content = response.read().decode()
            items = ET.fromstring(content).findall('./channel/item')
            assert len(items) == 0
            assert_no_leak(content)
        checked += 1
    with urlopen(base+'/sitemap.xml', timeout=30) as response:
        content = response.read().decode()
        assert all(day not in content for day in WITHHELD_DATES)
        assert_no_leak(content)
    checked += 1
    with urlopen(base+'/robots.txt', timeout=30) as response:
        assert 'Sitemap:' in response.read().decode()
    checked += 1
    print(f'{checked} database HTTP/RSC checks passed: uncleared editorial and private evidence withheld on every surface')


if __name__ == '__main__':
    check(os.getenv('WEB_URL', 'http://127.0.0.1:3000'))
