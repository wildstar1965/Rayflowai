"""Unit tests for the Qloo client with mocked HTTP (no network, no key needed)."""
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.qloo.client import QlooClient, QlooError, QlooConfigError, _results_list
from app.services.qloo import cache


@pytest.fixture(autouse=True)
def clear_qloo_cache():
    cache.clear_cache()
    yield
    cache.clear_cache()


def _session(responses):
    """Build a fake requests.Session whose .get returns queued responses."""
    session = Mock()
    session.get = Mock(side_effect=list(responses))
    return session


def _response(status, payload=None, headers=None):
    r = Mock()
    r.status_code = status
    r.headers = headers or {}
    r.json = Mock(return_value=payload if payload is not None else {})
    return r


def test_missing_key_raises_config_error():
    client = QlooClient(api_key='', base_url='https://hackathon.api.qloo.com', session=_session([]))
    with pytest.raises(QlooConfigError):
        client.search('Interstellar')


def test_search_sends_api_key_header_and_parses_results():
    session = _session([_response(200, {'results': [{'entity_id': 'x', 'name': 'Interstellar'}]})])
    client = QlooClient(api_key='secret', base_url='https://hackathon.api.qloo.com', session=session)
    results = client.search('Interstellar', types='urn:entity:movie')
    assert results and results[0]['name'] == 'Interstellar'
    _, kwargs = session.get.call_args
    assert kwargs['headers']['X-Api-Key'] == 'secret'
    assert 'Authorization' not in kwargs['headers']  # must NOT be a bearer token
    assert kwargs['params']['query'] == 'Interstellar'
    assert kwargs['params']['types'] == 'urn:entity:movie'


def test_insights_requires_filter_type():
    client = QlooClient(api_key='k', session=_session([]))
    with pytest.raises(QlooError):
        client.insights({'signal.interests.entities': 'x'})


def test_401_raises_clear_error_without_leaking_body():
    session = _session([_response(401, {'error': 'bad key sensitive detail'})])
    client = QlooClient(api_key='k', session=session)
    with pytest.raises(QlooError) as exc:
        client.search('x')
    assert exc.value.status == 401
    assert 'sensitive detail' not in str(exc.value)


def test_403_unsupported_entity_type():
    session = _session([_response(403, {})])
    client = QlooClient(api_key='k', session=session)
    with pytest.raises(QlooError) as exc:
        client.insights({'filter.type': 'urn:entity:music'})
    assert exc.value.status == 403


def test_429_retries_then_raises(monkeypatch):
    monkeypatch.setattr('app.services.qloo.client.time.sleep', lambda *_: None)
    session = _session([_response(429, headers={'Retry-After': '0'}),
                        _response(429), _response(429)])
    client = QlooClient(api_key='k', session=session)
    with pytest.raises(QlooError) as exc:
        client.search('x')
    assert exc.value.status == 429
    assert session.get.call_count == 3  # retried up to MAX_RETRIES


def test_transient_5xx_then_success(monkeypatch):
    monkeypatch.setattr('app.services.qloo.client.time.sleep', lambda *_: None)
    session = _session([_response(503), _response(200, {'results': [{'tag_id': 't', 'name': 'Sci-Fi'}]})])
    client = QlooClient(api_key='k', session=session)
    results = client.tags_search('sci-fi')
    assert results[0]['tag_id'] == 't'
    assert session.get.call_count == 2


def test_empty_results_is_not_an_error():
    session = _session([_response(200, {'results': []})])
    client = QlooClient(api_key='k', session=session)
    assert client.search('obscure title') == []


def test_results_list_handles_multiple_shapes():
    assert _results_list({'results': [{'a': 1}]}) == [{'a': 1}]
    assert _results_list({'results': {'entities': [{'b': 2}]}}) == [{'b': 2}]
    assert _results_list({'entities': [{'c': 3}]}) == [{'c': 3}]
    assert _results_list({'nothing': True}) == []
