"""Run separate fixture/browser or isolated PostgreSQL HTTP acceptance."""
from contextlib import ExitStack
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, WEB_URL=f'http://127.0.0.1:{port}', DATA_MODE=os.getenv('DATA_MODE', 'fixture'))
    for name in list(env):
        if name.startswith('OPENAI_'):
            env[name] = ''
    env['OPENAI_API_KEY'] = ''
    sys.path.insert(0, str(ROOT))
    with ExitStack() as stack:
        if env['DATA_MODE'] == 'database':
            from smoke_database_web import isolated_projection
            database = os.getenv('TEST_DATABASE_URL', '')
            env['DATABASE_URL'] = stack.enter_context(isolated_projection(
                database, isolated=os.getenv('WEB_SMOKE_ISOLATED_DB') == '1'))
            smoke = 'smoke_database_web.py'
            if os.getenv('RUN_BROWSER') == '1':
                raise ValueError('Fixture browser checks require a separate DATA_MODE=fixture server')
        elif env['DATA_MODE'] == 'fixture':
            smoke = 'smoke_web.py'
        else:
            raise ValueError('Explicit fixture or database smoke mode is required')
        with tempfile.TemporaryFile(mode='w+') as log:
            server = subprocess.Popen(['node', str(ROOT/'node_modules/next/dist/bin/next'),
                'start', '--hostname', '127.0.0.1', '--port', str(port)],
                cwd=ROOT/'apps/web', env=env, stdout=log, stderr=log)
            try:
                for attempt in range(30):
                    if server.poll() is not None:
                        raise RuntimeError('Production server exited before readiness')
                    try:
                        with urlopen(env['WEB_URL']+'/en', timeout=2) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(1)
                else:
                    raise RuntimeError('Production server readiness timed out')
                subprocess.run([sys.executable, str(ROOT/'tests'/smoke)], env=env, check=True)
                subprocess.run([sys.executable, str(ROOT/'tests/smoke_tracker_web.py')], env=env, check=True)
                if os.getenv('RUN_BROWSER') == '1':
                    subprocess.run(['node', str(ROOT/'apps/web/tests/browser-smoke.mjs')], env=env, check=True)
            except Exception:
                log.seek(0)
                print(log.read())
                raise
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill(); server.wait()


if __name__ == '__main__':
    run()
