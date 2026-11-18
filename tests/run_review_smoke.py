"""Real Chromium checks over artificial private reports; never enroll or publish."""
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.review.analysis import analyze, suggest
from services.review.render import render_preview, render_review
from tests.test_review_gate_bridge import approval, bridge, real_candidate


class DOM(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags=[]; self.text=[]; self.lang=None

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'html': self.lang=dict(attrs).get('lang')

    def handle_data(self, data):
        self.text.append(data)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def browser(executable, url, profile, screenshot=None):
    flags = ['--headless=new', '--no-first-run', '--no-default-browser-check',
             '--disable-background-networking', '--disable-extensions', '--disable-dev-shm-usage',
             '--password-store=basic', '--use-mock-keychain', '--user-data-dir='+str(profile)]
    flags += ['--screenshot='+str(screenshot), '--window-size=1280,900'] if screenshot else ['--dump-dom']
    safe_env = {'PATH','SYSTEMROOT','WINDIR','HOME','USERPROFILE','TEMP','TMP',
                'CHROME_DEVEL_SANDBOX','DISPLAY','LD_LIBRARY_PATH'}
    env = {key:value for key,value in os.environ.items() if key.upper() in safe_env}
    result = subprocess.run([executable, *flags, url], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=100, env=env)
    fallback = os.getenv('CI_CHROMIUM_NO_SANDBOX') == '1'
    if fallback:
        assert sys.platform == 'linux' and os.getenv('CI') == 'true' and os.getenv('GITHUB_ACTIONS') == 'true'
    if result.returncode and 'No usable sandbox!' in result.stderr and fallback:
        print('Explicit isolated GitHub report fixture sandbox fallback.', flush=True)
        result = subprocess.run([executable, '--no-sandbox', *flags, url], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=100, env=env)
    if result.returncode: raise RuntimeError('Artificial report browser failed; private browser stderr withheld')
    return result.stdout


def run():
    candidates = [os.getenv('BROWSER_EXECUTABLE'), os.getenv('CHROME_PATH'),
        'C:/Program Files/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
        '/opt/google/chrome/chrome', '/usr/bin/google-chrome', '/usr/bin/chromium']
    executable = next((name for name in candidates if name and Path(name).is_file()), None)
    if not executable: raise RuntimeError('Installed Chromium is required; review browser checks cannot be skipped')
    output = ROOT/'artifacts/review-browser'; output.mkdir(mode=0o700, parents=True, exist_ok=True)
    checked = 0
    with tempfile.TemporaryDirectory() as folder:
        private = Path(folder)
        issue = real_candidate()
        issue['stories'][0]['summary']['en'] = 'Artificial QA prose <script>globalThis.QA_INJECTED=true</script><img src="https://attack.example/tracker" onerror="alert(1)">'
        issue['stories'][0]['summary']['zh'] = '\u4eba\u5de5\u6d4b\u8bd5\u5185\u5bb9 <script>globalThis.QA_INJECTED=true</script>'
        render_review(issue, analyze(issue), suggest(issue), private/'report')
        public = bridge({'action':'project','issue':issue,'policy':approval(issue)})['issue']
        assert public is not None
        render_preview(public, private/'approved')
        render_preview(None, private/'withheld')
        server = ThreadingHTTPServer(('127.0.0.1',0), partial(QuietHandler,directory=str(private)))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = 'http://127.0.0.1:'+str(server.server_port)
            routes = ['report/index.html'] + [state+'/'+locale+'/'+page+'.html'
                for state in ('approved','withheld') for locale in ('en','zh')
                for page in ('index','digest','sources','archive')]
            for index, route in enumerate(routes):
                document = browser(executable, base+'/'+route, private/('browser-'+str(index)))
                dom = DOM(); dom.feed(document)
                assert not any(tag in {'script','img','iframe','object','embed','video','audio'} for tag,_ in dom.tags), route
                assert not any(key.lower().startswith('on') for _,attrs in dom.tags for key in attrs), route
                assert any(tag=='meta' and attrs.get('http-equiv')=='Content-Security-Policy' for tag,attrs in dom.tags), route
                text = ''.join(dom.text)
                if route.startswith('report/'):
                    assert 'PRIVATE_EN_EVIDENCE' in text and 'PRIVATE_ZH_EVIDENCE' in text
                    assert '<script>globalThis.QA_INJECTED=true</script>' in text
                    assert any(attrs.get('lang')=='zh' for _,attrs in dom.tags)
                else:
                    assert dom.lang == route.split('/')[1], route
                    assert 'PRIVATE_EN_EVIDENCE' not in text and 'PRIVATE_ZH_EVIDENCE' not in text
                    assert 'PRIVATE_UNKNOWN_' not in text
                    if route.startswith('withheld/'):
                        assert 'Synthetic editorial fixture' not in text and issue['title']['en'] not in text
                    if route == 'approved/en/digest.html':
                        assert '<script>globalThis.QA_INJECTED=true</script>' in text
                checked += 1
            for name, route in (('review','report/index.html'),('preview','approved/zh/digest.html'),('withheld','withheld/en/index.html')):
                screenshot=output/(name+'.png')
                browser(executable,base+'/'+route,private/('screenshot-'+name),screenshot)
                assert screenshot.is_file() and screenshot.stat().st_size>1000
                screenshot.chmod(0o600)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    (output/'report.json').write_text(json.dumps({'artificialOnly':True,'browserChecks':checked,'screenshots':3}))
    print(f'{checked} artificial report/preview browser checks passed; three screenshots; no enrollment or approval persisted')


if __name__ == '__main__':
    run()
