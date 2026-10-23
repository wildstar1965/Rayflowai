"""Hosted adapter contracts; network services are mocked, media processing is real."""
import base64
import io
import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from test_editor_integration import guests
from test_editor_optional import sign_in
from app.editor.context import workspace_id
from app.editor.providers import PROVIDERS, proxy_request
from app.editor.store import store, StorageUnavailable


@pytest.mark.parametrize('provider', [name for name, meta in PROVIDERS.items() if meta[1]])
def test_provider_transport_contract_uses_only_current_judge_key(guests, provider):
    a, b = guests
    key = 'contract:key-secret' if provider == 'higgsfield' else 'contract-key-secret'
    assert a.put('/api/editor/providers/' + provider, json={'key': key}).status_code == 200
    metadata = PROVIDERS[provider]
    response = MagicMock(status_code=200, headers={'content-type': 'application/json'}, text=json.dumps({'echo': key, 'ok': True}))
    token = workspace_id.set(a.get('/api/session').json()['workspace_id'])
    try:
        with patch('app.editor.providers.validate_url'), patch('app.editor.providers.requests.request', return_value=response) as transport:
            result = proxy_request(provider, 'https://' + metadata[1][0] + '/contract?api_key=browser-secret',
                                   headers={'Authorization': 'browser-secret', 'Cookie': 'private-cookie'})
            request = transport.call_args
            assert 'browser-secret' not in str(request) and 'private-cookie' not in str(request)
            assert not request.kwargs['allow_redirects']
            if provider == 'pixabay':
                assert 'key=' + key in request.args[1]
            else:
                assert request.kwargs['headers'][metadata[2]] == metadata[3] + key
            assert key not in json.dumps(result)
        workspace_id.set(b.get('/api/session').json()['workspace_id'])
        with patch('app.editor.providers.validate_url'), patch('app.editor.providers.requests.request') as transport:
            with pytest.raises(ValueError, match='key in Connections'):
                proxy_request(provider, 'https://' + metadata[1][0] + '/contract')
            transport.assert_not_called()
    finally:
        workspace_id.reset(token)


def test_depth_gradient_has_correct_pixels_and_owned_output(guests):
    from app.editor.surface import depth_gradient
    a, b = guests
    image = Image.fromarray(np.tile(np.arange(5, dtype=np.uint8) * 50, (5, 1)))
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    token = workspace_id.set(a.get('/api/session').json()['workspace_id'])
    try:
        result = depth_gradient({'source': {'base64': base64.b64encode(buffer.getvalue()).decode()}, 'options': {'normalStrength': 2}}, 'normal-contract')
    finally:
        workspace_id.reset(token)
    response = a.get(result['url'])
    pixels = np.asarray(Image.open(io.BytesIO(response.content)))
    assert pixels.shape == (5, 5, 3)
    assert pixels[2, 2, 0] < 70 and pixels[2, 2, 1] == 128 and pixels[2, 2, 2] > 220
    assert b.get(result['url']).status_code == 404


def test_notebook_mcp_initialization_queries_and_session_isolation(guests, monkeypatch):
    from app.editor.mcp import call
    a, b = guests
    monkeypatch.setenv('EDITOR_NOTEBOOKLM_URL', 'http://mcp.internal/mcp')
    a.put('/api/editor/providers/notebooklm', json={'key': 'notebook-token'})
    initialize = MagicMock(status_code=200, headers={'mcp-session-id': 'private-mcp-session', 'content-type': 'application/json'})
    initialize.json.return_value = {'result': {'protocolVersion': '2025-03-26'}}
    query = MagicMock(status_code=200, headers={'content-type': 'text/event-stream'}, text='event: message\ndata: {"result":{"content":[{"text":"answer"}]}}\n\n')
    token = workspace_id.set(a.get('/api/session').json()['workspace_id'])
    try:
        with patch('app.editor.mcp.requests.post', side_effect=[initialize, MagicMock(status_code=202), query]) as transport:
            assert call('initialize') == {'ok': True}
            assert call('tools/call', {'name': 'notebook_query', 'arguments': {'query': 'context'}})['content'][0]['text'] == 'answer'
            assert transport.call_args.kwargs['headers']['Mcp-Session-Id'] == 'private-mcp-session'
            assert transport.call_args.kwargs['headers']['Authorization'] == 'Bearer notebook-token'
        with pytest.raises(ValueError, match='listing and queries'):
            call('tools/call', {'name': 'delete_notebook'})
        workspace_id.set(b.get('/api/session').json()['workspace_id'])
        with pytest.raises(ValueError, match='token in Connections'):
            call('tools/list')
    finally:
        workspace_id.reset(token)


def test_signed_storage_scope_and_scratch_reconstruction(guests, monkeypatch):
    a, _ = guests
    identity = a.get('/api/session').json()['workspace_id']
    monkeypatch.setenv('SUPABASE_URL', 'https://project.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'server-only-test-secret')
    signed = MagicMock()
    signed.json.return_value = {'signedURL': '/object/sign/rayflow-private/owned?token=short-lived'}
    with patch.object(store, 'request', return_value=signed) as request:
        ticket = store.sign(identity, 'assets/large.mp4')
        assert request.call_args.args[1].endswith(identity + '/assets/large.mp4')
        assert request.call_args.kwargs['json'] == {'expiresIn': 900}
        assert ticket['url'].startswith('https://project.supabase.co/storage/v1/object/sign/')
        assert 'server-only-test-secret' not in json.dumps(ticket)
    with patch.object(store, 'request', return_value=MagicMock(content=b'restored-media')) as request:
        assert store.get_blob(identity, 'assets/restarted.mp4').read_bytes() == b'restored-media'
        assert request.call_args.args[1].endswith(identity + '/assets/restarted.mp4')
    with pytest.raises(ValueError):
        store.sign(identity, '../other-judge/file')


def test_google_download_auth_does_not_follow_redirect_to_cdn(guests):
    from app.editor.results import download_output
    a, _ = guests
    a.put('/api/editor/providers/gemini', json={'key': 'google-key-private'})
    redirect = MagicMock(status_code=302, headers={'location': 'https://storage.googleapis.com/result.mp4'})
    output = MagicMock(status_code=200, headers={'content-type': 'video/mp4'})
    output.iter_content.return_value = [b'movie']
    contexts = [MagicMock(), MagicMock()]
    contexts[0].__enter__.return_value = redirect; contexts[1].__enter__.return_value = output
    token = workspace_id.set(a.get('/api/session').json()['workspace_id'])
    try:
        with patch('app.editor.results.validate_url'), patch('app.editor.results.requests.get', side_effect=contexts) as get:
            assert download_output('gemini', 'https://generativelanguage.googleapis.com/v1beta/files/movie:download') == (b'movie', 'video/mp4')
            assert get.call_args_list[0].kwargs['headers'] == {'x-goog-api-key': 'google-key-private'}
            assert get.call_args_list[1].kwargs['headers'] == {}
    finally:
        workspace_id.reset(token)


def test_comfy_prompt_history_files_and_controls_are_isolated(guests):
    from app.editor.comfy import prepare, record
    a, b = guests
    token = workspace_id.set(a.get('/api/session').json()['workspace_id'])
    try:
        body, _ = prepare('/prompt', '', 'POST', json.dumps({'prompt': {'1': {'class_type': 'SaveImage', 'inputs': {'filename_prefix': '../escape'}}}}), None)
        assert json.loads(body)['prompt']['1']['inputs']['filename_prefix'].startswith('rayflow/' + workspace_id.get())
        record('/prompt', 'POST', {'status': 200, 'text': '{"prompt_id":"one"}'})
        prepare('/history/one', '', 'GET', None, None)
        history = {'status': 200, 'text': json.dumps({'one': {'outputs': {'1': {'images': [{'filename': 'result.png', 'subfolder': 'own'}]}}}, 'other': {'private': True}})}
        record('/history/one', 'GET', history)
        assert 'other' not in json.loads(history['text'])
        prepare('/view', 'filename=result.png&subfolder=own', 'GET', None, None)
        for path in ('/history', '/queue', '/interrupt', '/manager/install'):
            with pytest.raises(ValueError, match='operator access'):
                prepare(path, '', 'POST', '{}', None)
        with pytest.raises(ValueError, match='operator approval'):
            prepare('/prompt', '', 'POST', '{"prompt":{"1":{"class_type":"ExecuteShell"}}}', None)
        workspace_id.set(b.get('/api/session').json()['workspace_id'])
        for path, query in (('/history/one', ''), ('/view', 'filename=result.png&subfolder=own')):
            with pytest.raises(ValueError, match='does not belong'):
                prepare(path, query, 'GET', None, None)
    finally:
        workspace_id.reset(token)


def test_studio_transfer_and_team_copy_relink_filenames(guests):
    from app.editor.sequences import transfer
    from app.services.media import uploaded_path
    a, b = guests
    sign_in(a, 'media-owner'); sign_in(b, 'media-editor')
    project = a.post('/api/editor/projects', json={'name': 'Studio shared'}).json()
    workspace = a.get('/api/session').json()['workspace_id']
    store.put_blob(workspace, 'uploads/original.png', b'original-frame')
    reel = {'images': [{'filename': 'original.png', 'url': '/api/uploads/original.png', 'original_name': 'Original'}],
            'plan': {'color_strength': 0, 'clips': [{'image_url': 'original.png', 'start_time': 0, 'duration': 1}]}}
    sequence = {'id': 'reel-primary', 'kind': 'rayflow', 'name': 'Studio', 'document': reel, 'revision': 0}
    assert transfer(sequence, 'editor', project['id'])['mediaItems'][0]['path'] == '/api/uploads/original.png'
    assert a.put('/api/editor/projects/' + project['id'] + '/sequences/reel-primary', json={key: value for key, value in sequence.items() if key != 'id'}).status_code == 200
    team = a.post('/api/editor/teams', json={'name': 'Team'}).json()
    code = a.post('/api/editor/teams/' + team['id'] + '/invite', json={'role': 'editor'}).json()['code']
    b.post('/api/editor/teams/join', json={'code': code})
    shared = a.post('/api/editor/teams/' + team['id'] + '/share', json={'project_id': project['id']}).json()
    document = next(s for s in shared['sequences'] if s['kind'] == 'rayflow')['document']
    reference = document['images'][0]['filename']
    assert reference == document['images'][0]['url'] == document['plan']['clips'][0]['image_url']
    assert b.get(reference).content == b'original-frame'
    # Exercise the authenticated resolver used by Studio analysis and rendering.
    from app.editor.context import account
    token = workspace_id.set(b.get('/api/session').json()['workspace_id'])
    user = account.set({'id': 'media-editor', 'name': 'Editor'})
    try:
        resolved = uploaded_path(reference)
        assert resolved.read_bytes() == b'original-frame'
        assert resolved.name.startswith('shared_')
        assert store.get_blob(workspace_id.get(), 'uploads/' + resolved.name).read_bytes() == b'original-frame'
    finally:
        account.reset(user); workspace_id.reset(token)
