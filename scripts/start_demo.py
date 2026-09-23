"""Start a password-protected, temporary Cloudflare demo on Windows."""
import json
import base64
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'demo'


def creation_time(process):
    """Record Windows' process identity, so a later reused PID cannot be stopped."""
    import ctypes
    from ctypes import wintypes

    times = [wintypes.FILETIME() for _ in range(4)]
    get_times = ctypes.WinDLL('kernel32', use_last_error=True).GetProcessTimes
    get_times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    get_times.restype = wintypes.BOOL
    if not get_times(wintypes.HANDLE(int(process._handle)), *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)


def stop_tree(process):
    if process is not None and process.poll() is None:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        process.wait(timeout=10)


def main():
    if os.name != 'nt':
        raise SystemExit('This launcher targets Windows; see DEPLOYMENT.md.')
    binary = ROOT / '.cache' / 'bin' / 'cloudflared.exe'
    if not binary.exists():
        raise SystemExit('Install the official cloudflared executable in .cache/bin first.')
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not python.exists():
        raise SystemExit('Run scripts/setup.ps1 to install the project environment first.')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8000))
    CACHE.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(32)
    env = dict(os.environ, PUBLIC_MODE='true', APP_AUTH_USER='demo',
               APP_AUTH_PASSWORD=password, MAX_UPLOAD_MB='90',
               ALLOWED_HOSTS='127.0.0.1,localhost,*.trycloudflare.com')
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with (CACHE / 'app.log').open('w') as log:
        app = subprocess.Popen([str(python), '-m', 'uvicorn', 'main:app',
                                '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'],
                               cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
    tunnel = None
    try:
        app_created = creation_time(app)
        auth = base64.b64encode(f'demo:{password}'.encode()).decode('ascii')
        readiness = urllib.request.Request('http://127.0.0.1:8000/api/health',
                                           headers={'Authorization': f'Basic {auth}', 'X-Forwarded-Proto': 'https'})
        for _ in range(30):
            if app.poll() is not None:
                raise RuntimeError('App stopped; inspect .cache/demo/app.log')
            try:
                with urllib.request.urlopen(readiness, timeout=1) as response:
                    health = json.load(response)
                    if response.status == 200 and health.get('public_mode') and health.get('access_protected'):
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('App readiness timed out')
        with (CACHE / 'tunnel.log').open('w') as log:
            tunnel = subprocess.Popen([str(binary), 'tunnel', '--no-autoupdate', '--protocol',
                                       'http2', '--url', 'http://127.0.0.1:8000'], cwd=ROOT,
                                      stdout=log, stderr=log, creationflags=flags)
        tunnel_created = creation_time(tunnel)
        for _ in range(60):
            if tunnel.poll() is not None:
                raise RuntimeError('Tunnel stopped; inspect .cache/demo/tunnel.log')
            # api.trycloudflare.com also appears in error messages; it is not a demo URL.
            match = re.search(r'https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com',
                              (CACHE / 'tunnel.log').read_text(errors='replace'))
            if match:
                access = dict(url=match.group(), username='demo', password=password,
                              app_pid=app.pid, tunnel_pid=tunnel.pid,
                              app_created=app_created, tunnel_created=tunnel_created)
                (CACHE / 'access.json').write_text(json.dumps(access, indent=2), encoding='utf-8')
                print('Demo URL:', access['url'])
                print('Credentials: .cache/demo/access.json (ignored by git)')
                return
            time.sleep(1)
        raise RuntimeError('Tunnel URL timed out')
    except BaseException:
        try:
            stop_tree(tunnel)
        finally:
            stop_tree(app)
        raise


if __name__ == '__main__':
    main()
