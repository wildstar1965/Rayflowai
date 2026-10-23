import sys
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services import job_history as history


@pytest.fixture(autouse=True)
def history_db(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'DB_PATH', tmp_path / 'jobs.sqlite3')


def test_empty_metrics_are_zero_and_averages_unknown():
    data = history.analytics()
    assert data['exports'] == data['active_jobs'] == data['total_jobs'] == 0
    assert data['average_render_seconds'] is None
    assert data['success_rate'] is None


def test_real_lifecycle_formulas_and_restart_recovery():
    with patch.object(history.time, 'time', return_value=100): history.created('r', 'render')
    with patch.object(history.time, 'time', return_value=110): history.started('r')
    with patch.object(history.time, 'time', return_value=130): history.finished('r', 'completed', '/api/exports/r.mp4')
    history.created('f', 'render'); history.started('f'); history.finished('f', 'failed')
    history.created('t', 'transcription'); history.started('t'); history.finished('t', 'completed')
    history.created('c', 'creative'); history.finished('c', 'cancelled')
    history.created('a', 'creative')
    data = history.analytics()
    assert data['exports'] == data['caption_jobs'] == data['active_jobs'] == 1
    assert data['success_rate'] == pytest.approx(200 / 3)
    assert data['average_render_seconds'] == 20
    history.recover_interrupted()
    assert history.get('a')['status'] == 'interrupted'
    assert history.analytics()['active_jobs'] == 0
    assert history.get('r')['status'] == 'completed'


def test_duplicate_finish_cannot_rewrite_a_measurement():
    history.created('r', 'render'); history.started('r'); history.finished('r', 'completed')
    first = history.get('r')
    history.finished('r', 'failed')
    assert history.get('r') == first


def test_daily_activity_uses_finish_date_and_excludes_cancelled():
    today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    for identity, kind, status, days in [('r', 'render', 'completed', 0), ('t', 'transcription', 'completed', 1),
                                         ('f', 'creative', 'failed', 0), ('c', 'render', 'cancelled', 0),
                                         ('old', 'render', 'completed', 7)]:
        history.created(identity, kind)
        with patch.object(history.time, 'time', return_value=(today - timedelta(days=days)).timestamp()):
            history.finished(identity, status)
    data = history.analytics()
    assert len(data['daily_activity']) == 7
    assert data['daily_activity'][-1] == {'date': today.date().isoformat(), 'completed': 1, 'failed': 1, 'exports': 1}
    assert data['daily_activity'][-2]['completed'] == 1
    assert sum(day['completed'] for day in data['daily_activity']) == 2
    assert data['cancelled_jobs'] == 1
    assert data['exports'] == 2  # All-time metrics include older jobs.


def test_analytics_api_reports_storage_failure_without_internal_paths():
    from fastapi.testclient import TestClient
    from app.main import app
    with patch.object(history, 'database', side_effect=sqlite3.OperationalError('private database path')):
        response = TestClient(app).get('/api/analytics')
    assert response.status_code == 503
    assert 'private database path' not in response.text


def test_creative_worker_records_success_failure_and_recovery():
    import time
    from app.services.creative_jobs import start_job
    succeeded = start_job(lambda report: {'ready': True})
    def fail(report):
        raise ValueError('Invalid source')
    failed = start_job(fail)
    deadline = time.monotonic() + 10
    while history.analytics()['active_jobs'] and time.monotonic() < deadline:
        time.sleep(.02)
    assert history.get(succeeded)['status'] == 'completed'
    assert history.get(failed)['status'] == 'failed'
    assert history.analytics()['success_rate'] == 50
