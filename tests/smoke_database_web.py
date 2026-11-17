"""Read-only HTTP checks for a purpose-built, isolated PostgreSQL QA projection.

The NIST research snapshot is source-grounded; its mock editorial receipt exercises
visibility only and is never imported into production or presented as a new event.
"""
from copy import deepcopy
from contextlib import contextmanager
import html
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATE = '2024-04-15'
HIDDEN_DATES = ('2026-11-10', '2026-11-11', '2026-11-12', '2024-04-16', '2024-04-17', '2024-04-18', '2024-04-19')


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
        for route in ('', '/archive', '/search', '/search?q=NIST', '/methodology', '/privacy',
                      '/whatsnew', '/digest/'+PUBLIC_DATE, '/digest/'+PUBLIC_DATE+'/sources'):
            with urlopen(base+'/'+locale+route, timeout=30) as response:
                body = html.unescape(response.read().decode())
                assert response.status == 200 and f'lang="{locale}"' in body, route
                assert 'example.org/fixtures/' not in body and 'fixture-notice' not in body, route
                assert all('/digest/'+day not in body for day in HIDDEN_DATES), route
                if route in ('', '/archive', '/search?q=NIST'):
                    assert '/digest/'+PUBLIC_DATE in body, route
                if route.endswith('/sources'):
                    assert 'https://www.nist.gov/programs-projects/digital-twins-advanced-manufacturing' in body
            checked += 1
        for day in (*HIDDEN_DATES, 'not-a-real-issue'):
            for suffix in ('', '/sources'):
                try:
                    urlopen(base+'/'+locale+'/digest/'+day+suffix, timeout=30)
                    raise AssertionError('Private/synthetic/malformed edition became visible: '+day)
                except HTTPError as error:
                    assert error.code == 404
                checked += 1
        with urlopen(base+'/'+locale+'/rss.xml', timeout=30) as response:
            content = response.read().decode()
            items = ET.fromstring(content).findall('./channel/item')
            assert len(items) == 1 and PUBLIC_DATE in (items[0].findtext('link') or '')
            assert 'example.org/fixtures/' not in content
        checked += 1
    with urlopen(base+'/sitemap.xml', timeout=30) as response:
        content = response.read().decode()
        assert PUBLIC_DATE in content and all(day not in content for day in HIDDEN_DATES)
    checked += 1
    with urlopen(base+'/robots.txt', timeout=30) as response:
        assert 'Sitemap:' in response.read().decode()
    checked += 1
    print(f'{checked} database-mode HTTP checks passed: grounded public projection visible; private, synthetic and malformed rows hidden')


if __name__ == '__main__':
    check(os.getenv('WEB_URL', 'http://127.0.0.1:3000'))
