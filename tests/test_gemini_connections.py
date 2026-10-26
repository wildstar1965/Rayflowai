"""Gemini credentials, model selection and Studio edits with isolated storage."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app
from app.editor.store import store
from app.services import ai_provider


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    with TestClient(app) as client:
        assert client.post('/api/session').status_code == 200
        yield client


def remote_response(data, status=200):
    return Mock(status_code=status, json=lambda: data)


def model_info(model='gemini-2.5-flash'):
    return {'name': 'models/' + model, 'supportedGenerationMethods': ['generateContent']}


def gemini_row(client):
    return next(row for row in client.get('/api/editor/providers').json()['providers'] if row['id'] == 'gemini')


def save(client, model='gemini-2.5-flash'):
    assert client.put('/api/editor/providers/gemini', json={'key': 'test-gemini-key', 'model': model}).status_code == 200


def test_save_verify_switch_and_delete_preserve_workspace_privacy(client, monkeypatch):
    save(client, 'models/gemini-2.5-flash')
    assert 'gemini-2.5-pro' in gemini_row(client)['models']
    assert gemini_row(client)['model'] == 'gemini-2.5-flash'
    assert client.put('/api/settings', json={'values': {'AI_PROVIDER': 'gemini'}}).status_code == 200
    settings = client.get('/api/settings')
    assert settings.json()['ai_provider'] == 'gemini'
    assert settings.json()['gemini_configured'] and settings.json()['gemini_model'] == 'gemini-2.5-flash'
    identity = client.get('/api/session').json()['workspace_id']
    assert 'test-gemini-key' not in json.dumps(store.get('credentials', identity + ':gemini', identity))
    assert 'test-gemini-key' not in settings.text + client.get('/api/editor/providers').text
    other = TestClient(app)
    other.post('/api/session')
    assert not gemini_row(other)['configured']
    remote = Mock(return_value=remote_response(model_info()))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    result = client.post('/api/editor/providers/gemini/test', json={'model': 'gemini-2.5-flash'}).json()
    assert result['ok'] and result['verified'] and gemini_row(client)['tested']
    assert remote.call_args.args == ('GET', ai_provider.GEMINI_BASE + '/models/gemini-2.5-flash')
    assert remote.call_args.kwargs['headers']['x-goog-api-key'] == 'test-gemini-key'
    assert remote.call_args.kwargs['allow_redirects'] is False
    assert client.delete('/api/editor/providers/gemini').status_code == 200
    assert not client.get('/api/settings').json()['gemini_configured']
    assert not client.post('/api/editor/providers/gemini/test').json()['ok']


def test_draft_key_and_model_are_tested_without_saving_or_marking_old_key_verified(client, monkeypatch):
    remote = Mock(return_value=remote_response(model_info('gemini-2.5-pro')))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    patch = {'key': 'new-draft-key', 'model': 'gemini-2.5-pro'}
    assert client.post('/api/editor/providers/gemini/test', json=patch).json()['ok']
    assert remote.call_args.kwargs['headers']['x-goog-api-key'] == patch['key']
    assert not gemini_row(client)['configured']
    save(client)
    assert client.post('/api/editor/providers/gemini/test', json=patch).json()['ok']
    assert gemini_row(client)['model'] == 'gemini-2.5-flash' and not gemini_row(client)['tested']
    assert client.post('/api/editor/providers/gemini/test', json={'model': 'gemini-2.5-pro'}).json()['ok']
    assert remote.call_args.kwargs['headers']['x-goog-api-key'] == 'test-gemini-key'


@pytest.mark.parametrize('status,error,expected', [
    (400, {'message': 'API key not valid. test-secret'}, 'Google rejected'),
    (400, {'details': [{'reason': 'API_KEY_EXPIRED'}]}, 'Google rejected'),
    (403, {'message': 'Your API key was reported as leaked. test-secret'}, 'replacement'),
    (403, {'details': [{'reason': 'API_KEY_HTTP_REFERRER_BLOCKED'}]}, 'restrictions'),
    (403, {}, 'Credentials'), (404, {}, 'unavailable'), (429, {}, 'billing'), (503, {}, 'unavailable'),
])
def test_connection_errors_explain_the_problem_without_echoing_credentials(monkeypatch, status, error, expected):
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(return_value=remote_response({'error': error}, status)))
    result = ai_provider.test_connection('gemini', 'test-secret', 'gemini-2.5-flash')
    assert not result['ok'] and expected in result['message']
    assert 'test-secret' not in json.dumps(result)


def test_failed_saved_test_clears_verified_status(client, monkeypatch):
    save(client)
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(return_value=remote_response(model_info())))
    assert client.post('/api/editor/providers/gemini/test').json()['ok']
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(side_effect=requests.ConnectionError('test-gemini-key')))
    response = client.post('/api/editor/providers/gemini/test')
    assert not response.json()['ok'] and not gemini_row(client)['tested']
    assert 'test-gemini-key' not in response.text


def test_find_models_handles_pages_and_filters_non_text_models(client, monkeypatch):
    save(client)
    remote = Mock(side_effect=[
        remote_response({'models': [model_info(), model_info('gemini-2.5-flash-image'), {'name': 'models/gemini-embedding-001', 'supportedGenerationMethods': ['embedContent']}], 'nextPageToken': 'next'}),
        remote_response({'models': [model_info('gemini-2.5-pro'), model_info(), model_info('gemini-new-text-preview')]}),
    ])
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    result = client.get('/api/editor/providers/gemini/models')
    assert result.status_code == 200
    assert result.json()['models'] == ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-new-text-preview']
    assert remote.call_args.kwargs['params']['pageToken'] == 'next'
    assert client.put('/api/editor/providers/gemini', json={'model': 'models/gemini-new-text-preview'}).status_code == 200
    assert gemini_row(client)['model'] == 'gemini-new-text-preview'
    for model in ('../../secrets', 'gemini-2.5-flash?key=secret', 'https://example.com/model'):
        assert client.put('/api/editor/providers/gemini', json={'model': model}).status_code == 422


def test_studio_uses_saved_gemini_model_and_applies_validated_plan(client, monkeypatch):
    save(client, 'gemini-2.5-pro')
    client.put('/api/settings', json={'values': {'AI_PROVIDER': 'gemini'}})
    plan = {'explanation': 'Remove captions', 'actions': [{'type': 'remove_subtitles', 'params': {'all': True}}]}
    remote = Mock(return_value=remote_response({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
        {'text': 'internal reasoning', 'thought': True}, {'text': json.dumps(plan)},
    ]}}]}))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    original = {'duration_seconds': 4, 'clips': [{'id': 'a', 'image_url': 'a.mp4', 'start_time': 0, 'duration': 4}],
                'subtitles': [{'id': 'caption-a', 'text': 'Caption', 'start_time': 0, 'end_time': 2}]}
    response = client.post('/api/ai/plan', json={'command': 'Remove the captions', 'current_plan': original})
    assert response.status_code == 200, response.text
    assert response.json()['proposed_plan']['subtitles'] == []
    assert remote.call_args.args == ('POST', ai_provider.GEMINI_BASE + '/models/gemini-2.5-pro:generateContent')
    body = remote.call_args.kwargs['json']
    assert body['generationConfig']['responseMimeType'] == 'application/json'
    assert body['systemInstruction']['parts'] and body['contents'][0]['role'] == 'user'
    assert 'test-gemini-key' not in json.dumps(body)
    assert original['subtitles']  # Planning leaves the caller's original document intact.


@pytest.mark.parametrize('body', [
    {'candidates': []},
    {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{}'}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'not JSON'}]}}]},
])
def test_invalid_or_incomplete_generation_never_becomes_a_plan(monkeypatch, body):
    values = {'AI_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'test-key'}
    monkeypatch.setattr(ai_provider, 'setting', lambda key, default='': values.get(key, default))
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(return_value=remote_response(body)))
    with pytest.raises(ai_provider.ProviderError):
        ai_provider.generate_plan([{'role': 'system', 'content': 'Return JSON.'}, {'role': 'user', 'content': 'Edit.'}])
