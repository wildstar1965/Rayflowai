import base64
from unittest.mock import patch
from test_editor_integration import guests
from app.editor.store import store


def sign_in(client, identity):
    with patch('app.editor.accounts.auth_request', return_value={'access_token': 'secret-access', 'refresh_token': 'secret-refresh',
               'user': {'id': identity, 'email': identity + '@example.com', 'email_confirmed_at': '2026-01-01T00:00:00Z'}}):
        response = client.post('/api/editor/account/verify', json={'email': identity + '@example.com', 'code': '123456'})
    assert response.status_code == 200, response.text
    assert 'secret-access' not in response.text and 'secret-refresh' not in response.text


def test_account_attachment_preserves_guest_work_and_rotates_session(guests):
    a, b = guests
    project = a.post('/api/editor/projects', json={'name': 'Guest work'}).json()
    cookie = a.cookies.get('rayflow_session')
    sign_in(a, 'account-one')
    assert a.cookies.get('rayflow_session') != cookie
    assert a.get('/api/session').json()['guest'] is False
    assert a.get('/api/editor/projects/' + project['id']).status_code == 200
    assert b.get('/api/editor/projects/' + project['id']).status_code == 404
    assert a.post('/api/editor/account/workspace', json={'workspace_id': b.get('/api/session').json()['workspace_id']}).status_code == 404
    assert a.post('/api/editor/account/logout').status_code == 200
    assert a.get('/api/editor/projects/' + project['id']).status_code == 404


def test_team_viewers_can_read_shared_media_but_not_edit_or_view_keys(guests):
    a, b = guests
    sign_in(a, 'team-owner'); sign_in(b, 'team-viewer')
    team = a.post('/api/editor/teams', json={'name': 'Judging crew'}).json()
    invitation = a.post('/api/editor/teams/' + team['id'] + '/invite', json={'role': 'viewer'}).json()['code']
    assert b.post('/api/editor/teams/join', json={'code': invitation}).status_code == 200
    assert b.post('/api/editor/teams/join', json={'code': invitation}).status_code == 422
    project = a.post('/api/editor/projects', json={'name': 'Private edit'}).json()
    a.put('/api/editor/projects/' + project['id'] + '/files/media.txt', content=b'shared media')
    a.put('/api/editor/providers/gemini', json={'key': 'private-owner-key'})
    shared = a.post('/api/editor/teams/' + team['id'] + '/share', json={'project_id': project['id']}).json()
    route = '/api/editor/projects/' + shared['id']
    assert b.get(route).status_code == 200
    assert b.get(route + '/files/media.txt').content == b'shared media'
    assert b.get('/api/editor/projects/' + project['id']).status_code == 404
    assert b.put(route, json={'name': 'Unauthorized', 'project': {}, 'revision': shared['revision']}).status_code == 403
    assert b.put(route + '/files/media.txt', content=b'overwrite').status_code == 403
    assert b.post(route + '/file-ticket', json={'relativePath': 'objects/malicious.txt'}).status_code == 403
    assert a.get(route + '/files/media.txt').content == b'shared media'
    assert not next(row for row in b.get('/api/editor/providers').json()['providers'] if row['id'] == 'gemini')['configured']
    update = {'session': 'viewer-session', 'update': base64.b64encode(b'update').decode()}
    assert b.post('/api/editor/collaboration/' + shared['id'], json=update).status_code == 403
    assert b.post('/api/editor/collaboration/' + shared['id'], json={'session': 'viewer-session', 'presence': {}}).status_code == 200


def test_collaboration_documents_are_private_and_durable(guests):
    a, b = guests
    project = a.post('/api/editor/projects', json={'name': 'Collaboration'}).json()
    route = '/api/editor/collaboration/' + project['id']
    data = base64.b64encode(b'encoded-yjs-update').decode()
    request = {'session': 'browser-one', 'update': data}
    assert a.post(route, json=request).status_code == 200
    assert a.post(route, json=request).status_code == 200
    assert len(a.get(route).json()['updates']) == 1
    assert b.get(route).status_code == 404
    assert b.post(route, json=request).status_code == 404


def test_removed_storage_workflows_are_unreachable_and_preserve_records(guests):
    a, _ = guests
    workspace = a.get('/api/session').json()['workspace_id']
    # Removing the feature must not delete old data or unrelated auth records.
    store.put('cloud_credentials', workspace + ':dropbox', workspace, {'encrypted': 'legacy'})
    for method, path in [('GET', ''), ('POST', '/dropbox/start'), ('DELETE', '/dropbox'), ('GET', '/callback')]:
        assert a.request(method, '/api/editor/cloud' + path).status_code == 404
    response = a.post('/api/editor/jobs', json={'kind': 'cloud', 'payload': {}, 'submission_key': 'old-cloud'})
    assert response.status_code == 422
    assert store.get('cloud_credentials', workspace + ':dropbox', workspace)['encrypted'] == 'legacy'
