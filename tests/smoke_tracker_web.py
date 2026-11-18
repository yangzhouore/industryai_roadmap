"""Exercise the bilingual tracker against the loopback smoke server."""

import html
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from smoke_database_web import TRACKER_PRIVATE_MILESTONE, TRACKER_PRIVATE_PROJECT, assert_no_leak


def read(base, route, *, rsc=False):
    request = Request(base + route, headers={'Rsc': '1'} if rsc else {})
    try:
        with urlopen(request, timeout=30) as response:
            if rsc:
                assert 'text/x-component' in response.headers.get('Content-Type', ''), route
            return response.status, html.unescape(response.read().decode())
    except HTTPError as error:
        return error.code, html.unescape(error.read().decode())


def metadata(body, route, locale):
    assert f'lang="{locale}"' in body
    suffix = route[3:].split('?', 1)[0]
    links = re.findall(r'<link\b[^>]+>', body)
    assert any('rel="canonical"' in link and f'/{locale}{suffix}"' in link for link in links), route
    for language in ('en', 'zh'):
        assert any(f'hrefLang="{language}"' in link and f'/{language}{suffix}"' in link for link in links), route


def check(base, mode):
    if urlsplit(base).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Tracker HTTP checks require a loopback web server')
    checked = 0
    for locale in ('en', 'zh'):
        prefix = f'/{locale}/tracker'
        common = ('', '/companies', '/technologies', '/projects', '/companies/siemens', '/technologies/physical-ai')
        demo = ('/companies/demo-robotics', '/projects/demo-robot-handoff')
        fixture = mode == 'fixture'
        for suffix in (*common, *(demo if fixture else ())):
            for rsc in (False, True):
                route = prefix + suffix
                status, body = read(base, route, rsc=rsc)
                assert status == 200, (route, status)
                if not rsc:
                    metadata(body, route, locale)
                if fixture:
                    assert ('Demonstration data.' if locale == 'en' else '演示数据。') in body
                else:
                    assert_no_leak(body)
                    assert TRACKER_PRIVATE_MILESTONE not in body and TRACKER_PRIVATE_PROJECT not in body
                    assert 'data-status=' not in body
                    assert ('No public milestones yet.' if locale == 'en' else '暂无公开里程碑。') in body
                checked += 1

        if fixture:
            term = 'robot' if locale == 'en' else '机器人'
            status, results = read(base, prefix + '?' + urlencode({'q': term}))
            assert status == 200 and 'data-status="synthetic"' in results
            assert 'example.org/fixtures/' in results and ('Published' if locale == 'en' else '发布日期') in results
            status, project = read(base, prefix + '/projects/demo-robot-handoff')
            assert status == 200
            dates = re.findall(r'<time dateTime="([^"]+)"', project)
            assert dates, 'Project chronology needs machine-readable date values'
            first_milestone_dates = [re.search(r'<time dateTime="([^"]+)"', item)[1]
                                     for item in project.split('class="tracker-milestone"')[1:]]
            assert first_milestone_dates == sorted(first_milestone_dates, reverse=True)
            checked += 2
        status, misses = read(base, prefix + '?q=nomatchxyz')
        assert status == 200 and 'data-status=' not in misses
        assert ('No matching milestones.' if locale == 'en' else '没有与搜索匹配的里程碑。') in misses
        checked += 1

        invalid = ('/not-a-module', '/companies/not-a-company', '/technologies/not-a-technology',
                   '/projects/not-a-project', '/companies/siemens/extra')
        if not fixture:
            invalid += (*demo, '/projects/' + TRACKER_PRIVATE_PROJECT)
        for suffix in invalid:
            for rsc in (False, True):
                status, body = read(base, prefix + suffix, rsc=rsc)
                assert status == 404 or (rsc and 'NEXT_HTTP_ERROR_FALLBACK;404' in body), (suffix, status)
                if not fixture:
                    assert_no_leak(body)
                    assert TRACKER_PRIVATE_MILESTONE not in body
                checked += 1
    print(f'{checked} {mode} tracker HTTP/RSC checks passed')


if __name__ == '__main__':
    check(os.environ['WEB_URL'], os.environ['DATA_MODE'])
