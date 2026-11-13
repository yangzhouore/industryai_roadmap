"""Start an isolated production server, check routes, and stop the owned process."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
env = dict(os.environ, WEB_URL=f'http://127.0.0.1:{port}', DATA_MODE=os.getenv('DATA_MODE', 'fixture'))
with tempfile.TemporaryFile(mode='w+') as log:
    server = subprocess.Popen(['node',str(root / 'node_modules/next/dist/bin/next'),
                               'start','--hostname','127.0.0.1','--port',str(port)],
                              cwd=root / 'apps/web',env=env,stdout=log,stderr=log)
    try:
        for attempt in range(30):
            if server.poll() is not None:
                raise RuntimeError('Production server exited before readiness')
            try:
                with urlopen(env['WEB_URL'] + '/en',timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('Production server readiness timed out')
        subprocess.run([sys.executable,str(root / 'tests/smoke_web.py')],env=env,check=True)
        if os.getenv('RUN_BROWSER') == '1':
            subprocess.run(['node',str(root / 'apps/web/tests/browser-smoke.mjs')],env=env,check=True)
    except Exception:
        log.seek(0)
        print(log.read())
        raise
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
