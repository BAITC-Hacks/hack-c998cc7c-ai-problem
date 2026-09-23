"""Start a password-protected, temporary Cloudflare demo on Windows."""
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'demo'


def main():
    if os.name != 'nt':
        raise SystemExit('This launcher targets Windows; see DEPLOYMENT.md.')
    binary = ROOT / '.cache' / 'bin' / 'cloudflared.exe'
    if not binary.exists():
        raise SystemExit('Install the official cloudflared executable in .cache/bin first.')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8000))
    CACHE.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(32)
    env = dict(os.environ, PUBLIC_MODE='true', APP_AUTH_USER='demo',
               APP_AUTH_PASSWORD=password, MAX_UPLOAD_MB='90',
               ALLOWED_HOSTS='127.0.0.1,localhost,*.trycloudflare.com')
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with (CACHE / 'app.log').open('w') as log:
        app = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app',
                                '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'],
                               cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
    tunnel = None
    try:
        for _ in range(30):
            if app.poll() is not None:
                raise RuntimeError('App stopped; inspect .cache/demo/app.log')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('App readiness timed out')
        with (CACHE / 'tunnel.log').open('w') as log:
            tunnel = subprocess.Popen([str(binary), 'tunnel', '--no-autoupdate', '--protocol',
                                       'http2', '--url', 'http://127.0.0.1:8000'], cwd=ROOT,
                                      stdout=log, stderr=log, creationflags=flags)
        for _ in range(60):
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',
                              (CACHE / 'tunnel.log').read_text(errors='replace'))
            if match:
                access = dict(url=match.group(), username='demo', password=password,
                              app_pid=app.pid, tunnel_pid=tunnel.pid)
                (CACHE / 'access.json').write_text(json.dumps(access, indent=2), encoding='utf-8')
                print('Demo URL:', access['url'])
                print('Credentials: .cache/demo/access.json (ignored by git)')
                return
            if tunnel.poll() is not None:
                raise RuntimeError('Tunnel stopped; inspect .cache/demo/tunnel.log')
            time.sleep(1)
        raise RuntimeError('Tunnel URL timed out')
    except BaseException:
        if tunnel is not None:
            tunnel.terminate()
        app.terminate()
        raise


if __name__ == '__main__':
    main()
