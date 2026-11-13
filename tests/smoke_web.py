"""Run against an already-running web server: python tests/smoke_web.py."""
import os
from urllib.error import HTTPError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

base = os.getenv('WEB_URL', 'http://127.0.0.1:3000')
checked = 0
for locale in ('en', 'zh'):
    for route in ('', '/digest/2026-11-12', '/digest/2026-11-12/sources', '/archive',
                  '/search', '/search?q=inspection', '/search?q=nomatchxyz',
                  '/methodology', '/whatsnew', '/privacy'):
        url = base + '/' + locale + route
        print('Checking', url, flush=True)
        with urlopen(url, timeout=60) as response:
            text = response.read().decode('utf-8')
            assert response.status == 200, route
            assert '<html' in text and '<title>' in text, route
            assert 'lang="' + locale + '"' in text, route
            assert '????' not in text, route
            if 'nomatchxyz' in route:
                assert ('No matching stories.' if locale == 'en' else '\u6ca1\u6709\u5339\u914d\u7684\u6545\u4e8b\u3002') in text
            checked += 1
    with urlopen(base + '/' + locale + '/rss.xml', timeout=30) as response:
        root = ET.fromstring(response.read())
        assert len(root.findall('./channel/item')) == 3
        checked += 1
    try:
        urlopen(base + '/' + locale + '/digest/not-a-real-issue', timeout=30)
        raise AssertionError('Missing issue must be 404')
    except HTTPError as error:
        assert error.code == 404
for route, needle in (('/sitemap.xml', '<urlset'), ('/robots.txt', 'Sitemap:')):
    with urlopen(base + route, timeout=30) as response:
        assert needle in response.read().decode('utf-8')
        checked += 1
print(f'{checked} web route checks passed; missing editions return 404')
