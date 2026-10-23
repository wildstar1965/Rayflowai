import sys
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services import provider_settings as settings


@pytest.fixture(autouse=True)
def private_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_PATH', tmp_path / 'private' / 'providers.json')


def test_credentials_are_write_only_and_blank_preserves_them():
    settings.save_settings({'OPENROUTER_API_KEY': 'test-secret', 'OPENROUTER_MODEL': 'test/model'})
    settings.save_settings({'OPENROUTER_API_KEY': ''})
    assert settings.setting('OPENROUTER_API_KEY') == 'test-secret'
    assert settings.public_settings()['openrouter_configured']
    assert 'test-secret' not in str(settings.public_settings())


def test_bad_host_and_unknown_provider_are_rejected():
    for host in ['ftp://localhost', 'http://user:pass@localhost', 'http://remote.invalid', 'http://localhost/api', 'http://localhost:bad']:
        with pytest.raises(ValueError): settings.save_settings({'OLLAMA_HOST': host})
    with pytest.raises(ValueError): settings.save_settings({'AI_PROVIDER': 'unsupported'})


def test_corrupt_settings_are_not_overwritten():
    settings.SETTINGS_PATH.parent.mkdir()
    settings.SETTINGS_PATH.write_text('broken')
    with pytest.raises(ValueError): settings.save_settings({'OLLAMA_MODEL': 'qwen3:8b'})
    assert settings.SETTINGS_PATH.read_text() == 'broken'


def test_connection_test_really_calls_provider_and_checks_status(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-only')
    with patch.object(settings.requests, 'get', return_value=Mock(status_code=401)) as call:
        assert not settings.test_provider('openrouter')['ok']
        assert call.call_count == 1
    with patch.object(settings.requests, 'get', return_value=Mock(status_code=200, json=lambda: {'data': {}})):
        assert settings.test_provider('openrouter')['ok']
    with patch.object(settings.requests, 'get', side_effect=settings.requests.Timeout):
        assert 'timed out' in settings.test_provider('openrouter')['message']


def test_production_and_cross_origin_writes_are_denied(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    monkeypatch.setenv('RAYFLOW_ENV', 'production')
    assert client.put('/api/settings', json={'values': {'OLLAMA_MODEL': 'qwen3:8b'}}).status_code == 403
    monkeypatch.setenv('RAYFLOW_ENV', 'development')
    assert client.put('/api/settings', headers={'origin': 'https://untrusted.invalid'}, json={'values': {}}).status_code == 403
