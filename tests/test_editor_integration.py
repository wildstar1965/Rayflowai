"""Behavioral regression tests for hosted guest isolation and editor persistence."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app
from app.editor.store import store
from app.editor.context import workspace_id
from app.editor.providers import credential, validate_url


@pytest.fixture
def guests(tmp_path, monkeypatch):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    a, b = TestClient(app), TestClient(app)
    first = a.post('/api/session')
    second = b.post('/api/session')
    assert first.status_code == second.status_code == 200
    assert first.json()['workspace_id'] != second.json()['workspace_id']
    return a, b


def test_guest_cookie_and_session_restore(guests):
    a, _ = guests
    original = a.get('/api/session').json()['workspace_id']
    response = a.post('/api/session')
    assert response.json()['workspace_id'] == original
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert a.delete('/api/session').status_code == 200
    assert a.get('/api/editor/projects').status_code == 401


def test_document_revision_survives_file_upload_but_rejects_stale_editor(guests):
    a, _ = guests
    project = a.post('/api/editor/projects', json={'name': 'Timeline'}).json()
    route = '/api/editor/projects/' + project['id']
    assert a.put(route + '/files/media/first.txt', content=b'asset').status_code == 200
    saved = a.put(route, json={'name': 'Timeline', 'project': {'timelineClips': [{'id': 'new'}]},
                               'document_revision': project['document_revision']})
    assert saved.status_code == 200
    stale = a.put(route, json={'name': 'Stale', 'project': {}, 'document_revision': project['document_revision']})
    assert stale.status_code == 409
    assert a.get(route).json()['project']['timelineClips'] == [{'id': 'new'}]
    assert a.put(route, json={'project': {}}).status_code == 428


def test_shared_sequences_keep_full_schemas_and_archive_roundtrip(guests):
    a, b = guests
    project = a.post('/api/editor/projects', json={'name': 'Both workspaces'}).json()
    route = '/api/editor/projects/' + project['id']
    reel = {'projectName': 'Reel', 'plan': {'clips': [], 'unknown_future_effect': {'strength': 87}}, 'images': []}
    sequence = {'kind': 'rayflow', 'name': 'Reel', 'document': reel, 'revision': 0}
    assert a.put(route + '/sequences/reel-primary', json=sequence).status_code == 200
    assert a.put(route + '/sequences/reel-primary', json=sequence).status_code == 409
    assert b.put(route + '/sequences/reel-primary', json=sequence).status_code == 404
    assert a.put(route, json={'project': {'timelineTracks': [], 'metadata': {'future': True}},
                             'document_revision': 1}).status_code == 200
    record = a.get(route).json()
    assert len(record['sequences']) == 2
    archive = a.get(route + '/archive')
    imported = a.post('/api/editor/project-import', files={'file': ('shared.zip', archive.content)}).json()
    assert imported['sequences'] == record['sequences']
    assert next(row for row in imported['sequences'] if row['kind'] == 'rayflow')['document'] == reel


def test_provider_specific_secret_fields_are_rejected(guests):
    a, _ = guests
    for key in ('gemini_api_key', 'oauthRefreshToken', 'service_role_key'):
        response = a.put('/api/editor/preferences', json={'nested': {key: 'not-a-real-key'}})
        assert response.status_code == 422


def test_keys_are_encrypted_write_only_and_owned(guests):
    a, b = guests
    key = 'test-only-provider-secret-1234567890'
    response = a.put('/api/editor/providers/gemini', json={'key': key, 'model': 'example-model'})
    assert response.status_code == 200
    assert key not in response.text
    assert next(p for p in response.json()['providers'] if p['id'] == 'gemini')['configured']
    assert not next(p for p in b.get('/api/editor/providers').json()['providers'] if p['id'] == 'gemini')['configured']
    identity = a.get('/api/session').json()['workspace_id']
    record = store.get('credentials', identity + ':gemini', identity)
    assert key not in json.dumps(record)
    token = workspace_id.set(identity)
    try:
        assert credential('gemini') == key
    finally:
        workspace_id.reset(token)
    assert a.put('/api/editor/providers/gemini', json={'key': '', 'model': 'another-model'}).status_code == 200
    assert a.delete('/api/editor/providers/gemini').status_code == 200
    assert not next(p for p in a.get('/api/editor/providers').json()['providers'] if p['id'] == 'gemini')['configured']


def test_projects_files_and_archives_cannot_cross_guests(guests):
    a, b = guests
    project = a.post('/api/editor/projects', json={'name': 'Owned project', 'project': {'timelineClips': []}}).json()
    identity = project['id']
    assert a.put(f'/api/editor/projects/{identity}/files/media/note.txt', content=b'owned content').status_code == 200
    assert a.get(f'/api/editor/projects/{identity}/files/media/note.txt').content == b'owned content'
    assert b.get(f'/api/editor/projects/{identity}').status_code == 404
    assert b.get(f'/api/editor/projects/{identity}/files/media/note.txt').status_code == 404
    assert b.get(f'/api/editor/projects/{identity}/archive').status_code == 404
    assert b.delete(f'/api/editor/projects/{identity}').status_code == 404
    archive = a.get(f'/api/editor/projects/{identity}/archive')
    assert archive.status_code == 200
    imported = a.post('/api/editor/project-import', files={'file': ('project.zip', archive.content, 'application/zip')})
    assert imported.status_code == 200
    copy_id = imported.json()['id']
    assert copy_id != identity
    assert a.get(f'/api/editor/projects/{copy_id}/files/media/note.txt').content == b'owned content'


def test_revision_conflict_preserves_saved_work(guests):
    a, _ = guests
    original = a.post('/api/editor/projects', json={'name': 'First', 'project': {}}).json()
    path = '/api/editor/projects/' + original['id']
    assert a.put(path, json={'name': 'Saved', 'project': {'important': True}, 'revision': original['revision']}).status_code == 200
    assert a.put(path, json={'name': 'Stale', 'project': {}, 'revision': original['revision']}).status_code == 409
    assert a.get(path).json()['project'] == {'important': True}


def test_preferences_survive_session_restore_without_keys(guests):
    a, b = guests
    assert a.put('/api/editor/preferences', json={'setupComplete': True, 'editor': {'ui_mode_v1': 'pro'}}).status_code == 200
    assert a.post('/api/session').json()['preferences']['setupComplete'] is True
    assert not b.get('/api/session').json()['preferences'].get('setupComplete')
    assert a.put('/api/editor/preferences', json={'api_key': 'must-not-be-saved'}).status_code == 422


def test_cross_origin_mutation_is_rejected(guests):
    a, _ = guests
    assert a.put('/api/editor/providers/gemini', headers={'Origin': 'https://unrelated.example'}, json={'key': 'anything'}).status_code == 403


def test_private_and_nonprovider_network_targets_are_rejected():
    with pytest.raises(ValueError):
        validate_url('http://127.0.0.1/private', ['127.0.0.1'])
    with pytest.raises(ValueError):
        validate_url('https://other.example/path', ['api.provider.example'])
    with patch('app.editor.providers.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
        with pytest.raises(ValueError):
            validate_url('https://api.provider.example', ['api.provider.example'])


def test_asset_access_is_workspace_scoped(guests):
    a, b = guests
    result = a.post('/api/editor/assets', files={'file': ('note.txt', b'private asset', 'text/plain')})
    assert result.status_code == 200
    url = result.json()['url']
    assert a.get(url).content == b'private asset'
    assert b.get(url).status_code == 404


def test_jobs_are_idempotent_owned_and_reject_reused_keys(guests):
    a, b = guests
    with patch('app.editor.jobs.threading.Thread'):
        request = {'kind': 'provider', 'payload': {'provider': 'gemini', 'url': 'https://generativelanguage.googleapis.com/v1beta/models'}, 'submission_key': 'same-operation'}
        first = a.post('/api/editor/jobs', json=request)
        second = a.post('/api/editor/jobs', json=request)
        assert first.status_code == second.status_code == 200
        identity = first.json()['id']
        assert second.json()['id'] == identity
        assert b.get('/api/editor/jobs/' + identity).status_code == 404
        assert b.post('/api/editor/jobs/' + identity + '/cancel').status_code == 404
        request['payload']['method'] = 'DELETE'
        assert a.post('/api/editor/jobs', json=request).status_code == 422


def test_legacy_upload_and_job_isolation(guests):
    a, b = guests
    from PIL import Image
    import io
    image = io.BytesIO()
    Image.new('RGB', (20, 20), 'red').save(image, format='PNG')
    uploaded = a.post('/api/media/images', files=[('files', ('test.png', image.getvalue(), 'image/png'))])
    assert uploaded.status_code == 200
    url = uploaded.json()['images'][0]['url']
    assert a.get(url).status_code == 200
    assert b.get(url).status_code == 404


def test_shared_asset_archive_import_relinks_for_another_guest(guests):
    a, b = guests
    import io
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (20, 20), 'blue').save(image, format='PNG')
    item = a.post('/api/media/images', files=[('files', ('source.png', image.getvalue(), 'image/png'))]).json()['images'][0]
    project = a.post('/api/editor/projects', json={'name': 'Portable'}).json()
    sequence = {'kind': 'rayflow', 'name': 'Reel', 'revision': 0,
                'document': {'images': [item], 'plan': {'clips': [{'image_url': item['filename']}]}}}
    route = '/api/editor/projects/' + project['id']
    assert a.put(route + '/sequences/reel-primary', json=sequence).status_code == 200
    archive = a.get(route + '/archive')
    imported = b.post('/api/editor/project-import', files={'file': ('portable.zip', archive.content)}).json()
    restored = imported['sequences'][0]['document']
    new_item = restored['images'][0]
    assert new_item['url'] != item['url']
    assert b.get(new_item['url']).content == a.get(item['url']).content
    assert restored['plan']['clips'][0]['image_url'] == new_item['filename']
    assert a.get(new_item['url']).status_code == 404


@pytest.mark.parametrize('provider,host,header,prefix', [
    ('gemini', 'generativelanguage.googleapis.com', 'x-goog-api-key', ''),
    ('replicate', 'api.replicate.com', 'Authorization', 'Bearer '),
    ('fal', 'queue.fal.run', 'Authorization', 'Key '),
    ('xai', 'api.x.ai', 'Authorization', 'Bearer '),
    ('elevenlabs', 'api.elevenlabs.io', 'xi-api-key', ''),
    ('sonauto', 'api.sonauto.ai', 'Authorization', 'Bearer '),
    ('sonilo', 'api.sonilo.com', 'Authorization', 'Bearer '),
    ('ltx', 'api.ltx.video', 'Authorization', 'Bearer '),
    ('runway', 'api.dev.runwayml.com', 'Authorization', 'Bearer '),
    ('worldlabs', 'api.worldlabs.ai', 'WLT-Api-Key', ''),
    ('higgsfield', 'api.higgsfield.ai', 'Authorization', 'Key '),
    ('machgen', 'api.machgen.ai', 'Authorization', 'Bearer '),
    ('brave_search', 'api.search.brave.com', 'X-Subscription-Token', ''),
    ('unsplash', 'api.unsplash.com', 'Authorization', 'Client-ID '),
    ('sketchfab', 'api.sketchfab.com', 'Authorization', 'Token '),
    ('openrouter', 'openrouter.ai', 'Authorization', 'Bearer '),
])
def test_provider_transport_uses_owned_key_and_redacts_response(guests, provider, host, header, prefix):
    from app.editor.providers import proxy_request
    from unittest.mock import Mock
    a, b = guests
    key = 'fake-transport-key:private-for-test'
    a.put('/api/editor/providers/' + provider, json={'key': key})
    workspace = a.get('/api/session').json()['workspace_id']
    response = Mock(status_code=200, text=json.dumps({'echo': key}), headers={'content-type': 'application/json'})
    token = workspace_id.set(workspace)
    try:
        with patch('app.editor.providers.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('1.1.1.1', 443))]), \
             patch('app.editor.providers.requests.request', return_value=response) as request:
            result = proxy_request(provider, 'https://' + host + '/test', headers={'Authorization': 'untrusted-browser-token'})
            assert request.call_args.kwargs['headers'][header] == prefix + key
            assert 'untrusted-browser-token' not in json.dumps(request.call_args.kwargs['headers'])
            assert key not in json.dumps(result)
            assert request.call_args.kwargs['allow_redirects'] is False
    finally:
        workspace_id.reset(token)
    token = workspace_id.set(b.get('/api/session').json()['workspace_id'])
    try:
        assert credential(provider) == ''
    finally:
        workspace_id.reset(token)
