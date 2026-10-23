"""Run browser checks against isolated local services, without touching user servers."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def main():
    artifacts = ROOT / 'test_artifacts' / ('browser-' + uuid.uuid4().hex)
    artifacts.mkdir(parents=True)
    api_port, web_port = port(), port()
    api = f'http://127.0.0.1:{api_port}'
    web = f'http://127.0.0.1:{web_port}'
    env = {**os.environ, 'RAYFLOW_ENV': 'test', 'RAYFLOW_STORAGE_DIR': str(artifacts / 'storage'),
           'RAYFLOW_TEST_URL': web, 'RAYFLOW_API_PROXY_TARGET': api, 'PYTHONUTF8': '1',
           'RAYFLOW_PUBLIC_ORIGINS': web, 'CORS_ORIGINS': web,
           'TEMP': str(artifacts), 'TMP': str(artifacts)}
    processes, logs = [], []
    commands = [
        ([sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', str(api_port)], ROOT, api + '/api/health'),
        (['node', 'node_modules/vite/bin/vite.js',
          *(['--config', os.environ['RAYFLOW_TEST_VITE_CONFIG'], '--configLoader', 'native'] if os.getenv('RAYFLOW_TEST_VITE_CONFIG') else ['preview']),
          '--host', '127.0.0.1', '--port', str(web_port), '--strictPort'], ROOT / 'frontend', web),
    ]
    try:
        for index, (command, cwd, url) in enumerate(commands):
            log = (artifacts / f'server-{index}.log').open('w', encoding='utf-8')
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError(f'Test service did not start; inspect {artifacts}')
        # Also ensure the production preview forwards /api correctly.
        with urllib.request.urlopen(web + '/api/ready', timeout=15) as response:
            assert response.status == 200
        files = sys.argv[1:] or ['tests/test_integration_browser.py']
        return subprocess.call([sys.executable, '-m', 'pytest', *files, '-q', '--tb=short', '--basetemp', str(artifacts / 'pytest')], cwd=ROOT, env=env)
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
        print(f'Browser service artifacts: {artifacts}', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
