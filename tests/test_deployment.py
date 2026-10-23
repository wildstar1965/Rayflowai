import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.request_limits import RequestSizeLimit
from app.services import job_history, video_renderer as renderer


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, 'DB_PATH', tmp_path / 'jobs.sqlite3')


def test_production_requires_persistent_storage_and_ignores_dotenv(tmp_path):
    env = {**os.environ, 'RAYFLOW_ENV': 'production', 'RAYFLOW_STORAGE_DIR': '', 'PYTHONPATH': str(ROOT / 'backend')}
    result = subprocess.run([sys.executable, '-c', 'import app.core.config'], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'persistent mounted directory' in result.stderr
    env['RAYFLOW_STORAGE_DIR'] = str(tmp_path / 'persistent')
    env['CORS_ORIGINS'] = 'https://studio.example.test'
    result = subprocess.run([sys.executable, '-c', "from app.core.config import CORS_ORIGINS,STORAGE_DIR; print(CORS_ORIGINS); print(STORAGE_DIR)"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'localhost' not in result.stdout and 'studio.example.test' in result.stdout
    env['MAX_UPLOAD_MB'] = 'invalid'
    result = subprocess.run([sys.executable, '-c', 'import app.core.config'], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'MAX_UPLOAD_MB must be an integer' in result.stderr


@pytest.mark.parametrize('length', [None, b'12'])
def test_body_limit_rejects_chunked_and_declared_oversize(length):
    async def run():
        sent = []
        chunks = iter([{'type': 'http.request', 'body': b'abcdef', 'more_body': True}, {'type': 'http.request', 'body': b'ghijkl', 'more_body': False}])
        async def receive():
            return next(chunks)
        async def send(message):
            sent.append(message)
        async def app(scope, receive, send):
            while (await receive()).get('more_body'):
                pass
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})
        scope = {'type': 'http', 'method': 'POST', 'headers': [(b'content-length', length)] if length else []}
        await RequestSizeLimit(app, 10)(scope, receive, send)
        assert sent[0]['status'] == 413
    asyncio.run(run())


def test_readiness_checks_required_tools_without_optional_models():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import health_routes
    with patch.object(health_routes.subprocess, 'run', side_effect=OSError('private path')):
        response = TestClient(app).get('/api/ready')
    assert response.status_code == 503
    assert response.json()['checks'] == {'storage': True, 'ffmpeg': False, 'ffprobe': False}
    assert 'private path' not in response.text


def test_render_queue_bounds_active_workers_and_records_cancel(tmp_path, monkeypatch):
    from app.schemas.editing_plan import EditingPlan
    monkeypatch.setattr(renderer, 'EXPORT_DIR', tmp_path)
    monkeypatch.setattr(renderer, 'RENDER_QUEUE_LIMIT', 2)
    monkeypatch.setattr(renderer, '_RENDER_SLOTS', threading.BoundedSemaphore(1))
    release = threading.Event()
    entered = threading.Event()
    calls = []
    def worker(identity, *args):
        calls.append(identity)
        if renderer._JOBS[identity].status != 'cancelled':
            renderer._JOBS[identity].status = 'processing'
            job_history.started(identity)
            entered.set()
            release.wait(5)
            renderer._JOBS[identity].status = 'completed'
        job_history.finished(identity, renderer._JOBS[identity].status)
    with patch.object(renderer, '_render_worker', side_effect=worker):
        first = renderer.start_render_job(EditingPlan(), [])
        assert entered.wait(2)
        second = renderer.start_render_job(EditingPlan(), [])
        try:
            with pytest.raises(ValueError, match='queue is full'):
                renderer.start_render_job(EditingPlan(), [])
            assert calls == [first]
            assert renderer.cancel_render_job(second)
            with pytest.raises(ValueError, match='queue is full'):
                renderer.start_render_job(EditingPlan(), [])
        finally:
            release.set()
            deadline = time.monotonic() + 5
            while renderer._ACTIVE_RENDER_IDS and time.monotonic() < deadline:
                time.sleep(.01)
    assert job_history.get(first)['status'] == 'completed'
    assert job_history.get(second)['status'] == 'cancelled'
    assert not renderer._ACTIVE_RENDER_IDS


def test_render_timeout_kills_child_process(monkeypatch):
    from unittest.mock import Mock
    from app.schemas.editing_plan import RenderJobStatus
    monkeypatch.setitem(renderer._JOBS, 'timeout-test', RenderJobStatus(job_id='timeout-test', status='processing', progress=0, created_at=0))
    monkeypatch.setitem(renderer._RENDER_DEADLINES, 'timeout-test', time.monotonic() - 1)
    process = Mock()
    with patch.object(renderer.subprocess, 'Popen', return_value=process):
        with pytest.raises(RuntimeError, match='time limit'):
            renderer._run_render(['ffmpeg'], 'timeout-test')
    process.kill.assert_called_once()
    process.communicate.assert_called_once()


def test_production_startup_readiness_and_private_settings(tmp_path):
    env = {**os.environ, 'RAYFLOW_ENV': 'production', 'RAYFLOW_STORAGE_DIR': str(tmp_path / 'production'),
           'PYTHONPATH': str(ROOT / 'backend'), 'CORS_ORIGINS': 'https://studio.example.test'}
    script = '''
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/ready').status_code == 503  # Hosted storage/vault/runtime are not configured in this fixture.
    assert client.get('/docs').status_code == 404
    assert client.get('/api/settings').json()['editable'] is False
    assert client.put('/api/settings', json={'values': {'AI_PROVIDER': 'local'}}).status_code == 403
    assert client.get('/api/analytics').status_code == 401
print('Production startup, readiness, settings protection and empty analytics passed')
'''
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_completed_render_download_survives_registry_restart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import routes
    identity = 'aa123456'
    monkeypatch.setattr(routes, 'EXPORT_DIR', tmp_path)
    monkeypatch.setattr(renderer, '_JOBS', {})
    job_history.created(identity, 'render')
    job_history.started(identity)
    job_history.finished(identity, 'completed', f'/api/exports/rayflow_{identity}.mp4')
    (tmp_path / f'rayflow_{identity}.mp4').write_bytes(b'persisted export fixture')
    with TestClient(app) as client:
        assert client.get(f'/api/render/{identity}').json()['status'] == 'completed'
        assert client.get(f'/api/render/{identity}/download').content == b'persisted export fixture'


def test_creative_cancelled_workers_still_count_towards_admission(monkeypatch):
    from app.services import creative_jobs
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(creative_jobs, '_slots', slots)
    jobs = []
    try:
        jobs = [creative_jobs.start_job(lambda report: None) for _ in range(4)]
        for identity in jobs:
            assert creative_jobs.cancel_job(identity)
        with pytest.raises(ValueError, match='queue is full'):
            creative_jobs.start_job(lambda report: None)
    finally:
        slots.release()
        deadline = time.monotonic() + 5
        while creative_jobs._events and time.monotonic() < deadline:
            time.sleep(.01)
    assert not creative_jobs._events
    assert all(job_history.get(identity)['status'] == 'cancelled' for identity in jobs)
