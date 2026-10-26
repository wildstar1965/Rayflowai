"""Voice actions, shared local configuration, and gateway credential boundaries."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app
from app.editor.context import workspace_id
from app.editor import providers
from app.schemas.ai_editing import AIEditingPlan
from app.schemas.editing_plan import EditingPlan
from app.services import ai_editing, ai_provider, ollama_client, provider_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    client = TestClient(app)
    client.post('/api/session').raise_for_status()
    return client


def test_ollama_address_and_model_are_shared(client, monkeypatch):
    monkeypatch.delenv('EDITOR_OLLAMA_URL', raising=False)
    monkeypatch.setenv('OLLAMA_HOST', 'http://127.0.0.1:11434')
    client.put('/api/editor/providers/ollama', json={'model': 'qwen3:8b'}).raise_for_status()
    assert client.get('/api/settings').json()['ollama_model'] == 'qwen3:8b'
    row = next(p for p in client.get('/api/editor/providers').json()['providers'] if p['id'] == 'ollama')
    assert row['configured'] and row['base_url'] == 'http://127.0.0.1:11434'
    client.put('/api/settings', json={'values': {'OLLAMA_MODEL': 'other-model'}}).raise_for_status()
    row = next(p for p in client.get('/api/editor/providers').json()['providers'] if p['id'] == 'ollama')
    assert row['model'] == 'other-model'
    client.put('/api/editor/providers/ollama', json={'model': ''}).raise_for_status()
    assert client.get('/api/settings').json()['ollama_model'] == ''


def test_editor_ollama_override_is_an_operator_approved_host(client, monkeypatch):
    monkeypatch.setenv('EDITOR_OLLAMA_URL', 'https://models.example.test')
    assert client.get('/api/settings').json()['ollama_host'] == 'https://models.example.test'
    assert provider_settings.validate_host('https://models.example.test') == 'https://models.example.test'


def test_local_default_does_not_enable_unconfigured_production(monkeypatch):
    monkeypatch.delenv('EDITOR_OLLAMA_URL', raising=False)
    monkeypatch.delenv('OLLAMA_HOST', raising=False)
    monkeypatch.setenv('RAYFLOW_ENV', 'development')
    assert providers.local_provider_url('ollama') == 'http://127.0.0.1:11434'
    monkeypatch.setenv('RAYFLOW_ENV', 'production')
    assert providers.local_provider_url('ollama') == ''


def test_agentrouter_draft_key_is_only_sent_to_router(client, monkeypatch):
    remote = Mock(return_value=Mock(status_code=401))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    result = client.post('/api/editor/providers/agentrouter/test', json={'key': 'draft-only-secret', 'model': 'gpt-6-astra'})
    assert not result.json()['ok']
    assert 'draft-only-secret' not in result.text
    assert remote.call_args.args[1] == 'https://agentrouter.org/v1/chat/completions'
    assert remote.call_args.kwargs['headers']['Authorization'] == 'Bearer draft-only-secret'
    assert remote.call_args.kwargs['allow_redirects'] is False
    assert not next(p for p in client.get('/api/editor/providers').json()['providers'] if p['id'] == 'agentrouter')['configured']


def test_agentrouter_selected_transport_uses_saved_workspace_key(client, monkeypatch):
    client.put('/api/editor/providers/agentrouter', json={'key': 'saved-test-secret', 'model': 'claude-opus-5-5'}).raise_for_status()
    client.put('/api/settings', json={'values': {'AI_PROVIDER': 'agentrouter'}}).raise_for_status()
    payload = {'explanation': 'Rotate the picture', 'actions': [{'type': 'transform_clip', 'params': {'clip_id': 'a', 'rotation': 90}}]}
    remote = Mock(return_value=Mock(status_code=200, json=lambda: {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(payload)}}]}))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    response = client.post('/api/ai/plan', json={'command': 'Rotate selected clip', 'current_plan': project().model_dump(), 'context': {'selected_clip_id': 'a'}})
    assert response.status_code == 200, response.text
    assert remote.call_args.args[1] == 'https://agentrouter.org/v1/chat/completions'
    assert remote.call_args.kwargs['json']['model'] == 'claude-opus-5-5'
    assert 'saved-test-secret' not in client.get('/api/editor/providers').text


def project():
    return EditingPlan(duration_seconds=4, clips=[dict(id='a', image_url='a.png', start_time=0, duration=4, rotation=30)])


def test_relative_transform_preserves_media_and_is_transactional():
    original = project()
    proposal = AIEditingPlan(explanation='Move and rotate', actions=[dict(type='transform_clip', params={'clip_id': 'a', 'rotation': 90, 'offset_x': .05, 'relative': True})])
    edited, _ = ai_editing.apply_actions(original, proposal)
    assert edited.clips[0].rotation == 120 and edited.clips[0].offset_x == .05
    assert edited.clips[0].duration == 4 and edited.clips[0].image_url == 'a.png'
    assert original.clips[0].rotation == 30 and original.clips[0].offset_x == 0
    invalid = proposal.model_copy(deep=True)
    invalid.actions[0].params['offset_x'] = 1
    with pytest.raises(ai_editing.AIEditingError):
        ai_editing.apply_actions(edited, invalid)
    assert edited.clips[0].offset_x == .05


@pytest.mark.parametrize('params', [{'rotation': float('nan')}, {'offset_x': 2}, {'rotation': 'huge'}, {}])
def test_invalid_transforms_are_rejected(params):
    with pytest.raises(ValueError):
        AIEditingPlan(explanation='Invalid', actions=[dict(type='transform_clip', params={'clip_id': 'a', **params})])


def test_local_prompt_and_inference_preserve_action_contract(monkeypatch):
    monkeypatch.setattr(ai_editing, 'setting', lambda *_: 'ollama')
    monkeypatch.setattr(ai_provider, 'selected_provider', lambda: 'ollama')
    generate = Mock(return_value=json.dumps({'explanation': 'Rotate', 'actions': [{'type': 'transform_clip', 'params': {'clip_id': 'a', 'rotation': 90}}]}))
    monkeypatch.setattr(ollama_client, 'generate_ollama', generate)
    plan = ai_editing.request_plan('Rotate selected clip', project())
    assert plan.actions[0].type == 'transform_clip'
    assert len(generate.call_args.args[0]) < 8000
    assert generate.call_args.kwargs['context_size'] == 8192


def test_ollama_memory_error_is_actionable_and_redacted(monkeypatch):
    monkeypatch.setattr(ollama_client, 'check_ollama_status', lambda _: ollama_client.OllamaStatusResponse(available=True, ready=True, host='http://127.0.0.1:11434', models=['model'], default_model='model'))
    monkeypatch.setattr(ollama_client.requests, 'post', Mock(return_value=Mock(status_code=500, json=lambda: {'error': 'secret path: unable to allocate CPU_REPACK buffer'})))
    with pytest.raises(ollama_client.OllamaError, match='enough memory') as error:
        ollama_client.generate_ollama('Hello')
    assert 'secret path' not in str(error.value)
