"""Transport, configuration and API contract tests; no running model required."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services import ollama_client as ollama, provider_settings as settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_PATH', tmp_path / 'providers.json')
    monkeypatch.setenv('RAYFLOW_ENV', 'development')
    monkeypatch.setenv('OLLAMA_HOST', 'http://127.0.0.1:11434')
    monkeypatch.setenv('OLLAMA_MODEL', '')
    monkeypatch.setenv('OLLAMA_GENERATION_TIMEOUT', '180')


def tags(*models):
    return Mock(status_code=200, json=lambda: {'models': [{'name': m} for m in models]})


def test_saved_endpoint_model_and_reconnection_take_effect_without_restart():
    settings.save_settings({'OLLAMA_HOST': 'http://127.0.0.1:11435', 'OLLAMA_MODEL': 'second:latest'})
    with patch.object(ollama.requests, 'get', return_value=tags('first:latest', 'second:latest')) as request:
        status = ollama.check_ollama_status()
        assert status.ready and status.default_model == 'second:latest'
        assert request.call_args.args[0] == 'http://127.0.0.1:11435/api/tags'
        settings.save_settings({'OLLAMA_HOST': 'http://127.0.0.1:11436', 'OLLAMA_MODEL': ''})
        assert ollama.check_ollama_status().default_model == 'first:latest'
        assert request.call_args.args[0] == 'http://127.0.0.1:11436/api/tags'


def test_invalid_model_never_sends_prompt_or_substitutes():
    settings.save_settings({'OLLAMA_MODEL': 'missing'})
    with patch.object(ollama.requests, 'get', return_value=tags('installed')), patch.object(ollama.requests, 'post') as post:
        status = ollama.check_ollama_status()
        assert status.available and not status.ready
        assert status.default_model == 'missing'
        with pytest.raises(ollama.OllamaError, match='not installed'):
            ollama.generate_ollama('prompt')
        post.assert_not_called()


def test_empty_server_has_setup_instructions():
    with patch.object(ollama.requests, 'get', return_value=tags()):
        status = ollama.check_ollama_status()
    assert status.available and not status.ready and 'ollama pull' in status.error


def test_correct_generation_protocol_and_response():
    with patch.object(ollama.requests, 'get', return_value=tags('qwen3:8b')), patch.object(
        ollama.requests, 'post', return_value=Mock(status_code=200, json=lambda: {'done': True, 'response': '{"title_text":"Morning"}'})
    ) as post:
        assert ollama.generate_ollama('prompt') == '{"title_text":"Morning"}'
        payload = post.call_args.kwargs['json']
        assert payload['model'] == 'qwen3:8b' and payload['stream'] is False and payload['format'] == 'json'
        assert post.call_args.kwargs['timeout'] == (3, 180)
        assert post.call_args.kwargs['allow_redirects'] is False


@pytest.mark.parametrize('body', [{}, {'done': False, 'response': 'partial'}, {'done': True, 'response': ''}, []])
def test_incomplete_or_invalid_generation_is_not_success(body):
    with patch.object(ollama.requests, 'get', return_value=tags('model')), patch.object(
        ollama.requests, 'post', return_value=Mock(status_code=200, json=lambda: body)
    ):
        with pytest.raises(ollama.OllamaError):
            ollama.generate_ollama('prompt')


def test_discovery_retry_is_bounded_and_timeout_is_not_retried():
    with patch.object(ollama.requests, 'get', side_effect=ollama.requests.ConnectionError('internal host details')) as get:
        status = ollama.check_ollama_status()
        assert not status.available and get.call_count == 2
        assert 'internal host details' not in status.error
    with patch.object(ollama.requests, 'get', side_effect=ollama.requests.Timeout) as get:
        assert 'timed out' in ollama.check_ollama_status().error
        assert get.call_count == 1


def test_inference_timeout_is_not_replayed():
    with patch.object(ollama.requests, 'get', return_value=tags('model')), patch.object(ollama.requests, 'post', side_effect=ollama.requests.Timeout) as post:
        with pytest.raises(ollama.OllamaError) as failure:
            ollama.generate_ollama('prompt')
        assert failure.value.status_code == 504 and post.call_count == 1


def test_operator_allowed_https_host_and_redirects(monkeypatch):
    monkeypatch.setenv('OLLAMA_ALLOWED_HOSTS', 'https://models.example.test')
    settings.save_settings({'OLLAMA_HOST': 'https://models.example.test'})
    with patch.object(ollama.requests, 'get', return_value=Mock(status_code=302)) as get:
        assert not ollama.check_ollama_status().available
        assert get.call_args.kwargs['allow_redirects'] is False
    with patch.object(ollama.requests, 'get') as get:
        assert not ollama.check_ollama_status('https://unapproved.example.test').available
        get.assert_not_called()


def test_prompt_endpoint_returns_real_response_and_validation_errors():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.routes import _ai_requests
    _ai_requests.clear()
    client = TestClient(app)
    with patch.object(ollama.requests, 'get', return_value=tags('model')), patch.object(
        ollama.requests, 'post', return_value=Mock(status_code=200, json=lambda: {'done': True, 'response': 'Ready'})
    ) as post:
        response = client.post('/api/ollama/test', json={'model': 'model'})
        assert response.status_code == 200 and response.json() == {'response': 'Ready'}
        assert post.call_count == 1
        assert client.post('/api/ollama/test', json={'model': 'missing'}).status_code == 422
        assert post.call_count == 1


def test_production_settings_ignore_development_credentials(monkeypatch):
    settings.save_settings({'OLLAMA_MODEL': 'developer-model', 'OPENROUTER_API_KEY': 'developer-key'})
    monkeypatch.setenv('RAYFLOW_ENV', 'production')
    monkeypatch.setenv('OLLAMA_MODEL', 'production-model')
    monkeypatch.setenv('OPENROUTER_API_KEY', '')
    assert settings.setting('OLLAMA_MODEL') == 'production-model'
    assert not settings.public_settings()['openrouter_configured']


def test_interpretation_parses_validated_model_result():
    from app.schemas.editing_plan import EditingPlan
    with patch.object(ollama, 'generate_ollama', return_value='{"aspect_ratio":"1:1","explanation":"Square frame"}'):
        result = ollama.interpret_with_ollama('square composition', EditingPlan(), strict=True)
    assert result.plan.aspect_ratio == '1:1'
    assert result.applied_changes == ['Set aspect ratio to 1:1']


def test_local_command_preference_never_contacts_a_provider():
    from fastapi.testclient import TestClient
    from app.main import app
    settings.save_settings({'AI_PROVIDER': 'local'})
    with patch.object(ollama, 'interpret_with_ollama', side_effect=AssertionError('Provider must not run')):
        response = TestClient(app).post('/api/commands/interpret', json={'command': 'an unusual artistic instruction', 'current_plan': {}})
    assert response.status_code == 200


def test_discovery_rejects_malformed_json_and_checks_http_status():
    for response in [Mock(status_code=200, json=lambda: {}), Mock(status_code=200, json=Mock(side_effect=ValueError())), Mock(status_code=401)]:
        with patch.object(ollama.requests, 'get', return_value=response):
            assert not ollama.check_ollama_status().available
