"""Integration tests for the taste routes using TestClient and mocked Qloo.

These exercise the real FastAPI stack (session, workspace scoping, persistence)
but stub the Qloo network layer so no key or internet is required.
"""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    c = TestClient(app)
    assert c.post('/api/session').status_code == 200
    return c


PREFS = {'preferences': [
    {'text': 'Interstellar', 'category': 'movie'},
    {'text': 'Hans Zimmer', 'category': 'artist'},
    {'text': 'atmospheric', 'category': 'mood'},
], 'use_qloo': True}


def test_profile_requires_session(tmp_path, monkeypatch):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    anon = TestClient(app)
    # No session established -> 401.
    assert anon.get('/api/taste/profile').status_code == 401


def test_declared_only_profile_without_qloo_key(client):
    # No QLOO_API_KEY configured -> declared-only, still works.
    created = client.post('/api/taste/profile', json=PREFS)
    assert created.status_code == 200
    body = created.json()
    assert body['exists'] is True
    assert body['profile']['source'] == 'declared_only'
    assert body['qloo_configured'] is False

    fetched = client.get('/api/taste/profile')
    assert fetched.status_code == 200 and fetched.json()['exists'] is True


def test_profile_uses_mocked_qloo_when_key_present(client, monkeypatch):
    monkeypatch.setenv('QLOO_API_KEY', 'test-key')

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def search(self, query, *, types=None, take=5, extra=None):
            return [{'entity_id': 'urn:' + query, 'name': query, 'type': types or 'urn:entity:movie',
                     'popularity': 0.9}]

        def tags_search(self, query, *, take=10, extra=None):
            return [{'tag_id': 'urn:tag:' + query, 'name': query}]

        def insights(self, params):
            return {'results': [{'entity_id': 'urn:dunkirk', 'name': 'Dunkirk', 'affinity': 0.9}]}

    with patch('app.services.qloo.profile_builder.QlooClient', FakeClient), \
         patch('app.services.qloo.entity_resolver.QlooClient', FakeClient), \
         patch('app.services.qloo.taste_analyzer.QlooClient', FakeClient):
        created = client.post('/api/taste/profile', json=PREFS)
    assert created.status_code == 200
    body = created.json()
    assert body['qloo_configured'] is True
    assert body['profile']['source'] == 'qloo'
    assert any(a['name'] == 'Dunkirk' for a in body['profile']['cultural_associations'])


def test_edit_plan_requires_saved_profile(client):
    missing = client.post('/api/taste/edit-plan', json={'allow_llm': True})
    assert missing.status_code == 404
    client.post('/api/taste/profile', json=PREFS)
    strategy = client.post('/api/taste/edit-plan', json={'allow_llm': True})
    assert strategy.status_code == 200
    data = strategy.json()
    assert data['strategy']['color_mood'] in ('cinematic', 'vintage', 'noir', 'vibrant', 'minimal')
    assert data['used_llm'] is False  # no LLM key in tests


def test_apply_returns_proposed_plan_for_review(client):
    client.post('/api/taste/profile', json=PREFS)
    plan = {
        'duration_seconds': 6, 'aspect_ratio': '9:16', 'fit_mode': 'fill', 'style': 'vibrant',
        'beat_sync': True, 'cut_pacing': 'balanced', 'motion': 'dynamic',
        'title': {'enabled': False, 'text': ''},
        'clips': [
            {'id': 'a', 'image_url': '/api/uploads/a.jpg', 'start_time': 0, 'duration': 3, 'media_type': 'image'},
            {'id': 'b', 'image_url': '/api/uploads/b.jpg', 'start_time': 3, 'duration': 3, 'media_type': 'image'},
        ],
        'transitions': [],
    }
    resp = client.post('/api/taste/apply', json={'current_plan': plan, 'allow_llm': True})
    assert resp.status_code == 200
    body = resp.json()
    # A proposed plan is returned for approval; nothing is auto-applied/persisted.
    assert 'proposed_plan' in body and 'strategy' in body
    assert body['proposed_plan']['style'] in ('cinematic', 'vintage', 'noir', 'vibrant', 'minimal')


def test_taste_context_injection_ignores_client_supplied_value(client, monkeypatch):
    # The /api/ai/plan route must overwrite any client-sent taste_profile with
    # the server's saved one (or None), so taste context is not spoofable.
    from app.api.routes import _inject_taste_context
    from app.schemas.ai_editing import EditorContext
    from app.editor.context import workspace_id
    # Simulate no saved profile for the active workspace.
    forged = EditorContext(taste_profile={'declared': [{'text': 'FORGED'}]})
    workspace_id.set('nonexistent-workspace')
    result = _inject_taste_context(forged)
    assert result.taste_profile is None
