import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from test_editor_integration import guests
from app.editor.context import workspace_id
from app.editor.store import store
from app.editor import jobs


def test_sequence_transfer_preserves_original_and_rejects_lost_effects(guests):
    a, b = guests
    project = a.post('/api/editor/projects', json={'name': 'Transfer'}).json()
    route = '/api/editor/projects/' + project['id']
    reel = {'projectName': 'Reel', 'plan': {'color_strength': 0, 'aspect_ratio': '16:9',
            'clips': [{'id': 'original', 'image_url': '/api/uploads/test.png', 'start_time': 0,
                       'duration': 2, 'motion': 'static', 'transition': 'none', 'media_type': 'image'}]}}
    assert a.put(route + '/sequences/reel-primary', json={'kind': 'rayflow', 'name': 'Reel', 'revision': 0, 'document': reel}).status_code == 200
    record = a.get(route).json()
    result = a.post(route + '/sequences/reel-primary/transfer', json={'kind': 'editor', 'revision': record['revision']})
    assert result.status_code == 200, result.text
    transferred = result.json()
    assert transferred['document']['timelineClips'][0]['end'] == 2
    assert transferred['document']['rayflowTransfer']['originalDocument'] == reel
    record = a.get(route).json()
    assert record['sequences'][0]['document'] == reel
    assert b.post(route + '/sequences/reel-primary/transfer', json={'kind': 'editor', 'revision': record['revision']}).status_code == 404
    activated = a.post(route + '/sequences/' + transferred['id'] + '/activate', json={'revision': record['revision']})
    assert activated.status_code == 200
    assert activated.json()['project']['project']['mediaItems'][0]['path'] == '/api/uploads/test.png'
    reel['plan']['clips'][0]['motion'] = 'zoom_in'
    a.put(route + '/sequences/reel-primary', json={'kind': 'rayflow', 'name': 'Reel', 'revision': 1, 'document': reel})
    record = a.get(route).json()
    rejected = a.post(route + '/sequences/reel-primary/transfer', json={'kind': 'editor', 'revision': record['revision']})
    assert rejected.status_code == 422
    assert 'motion' in rejected.json()['detail']
    assert a.get(route).json() == record


def test_preferences_merge_keeps_unrelated_workspace_choices(guests):
    a, _ = guests
    a.patch('/api/editor/preferences', json={'editor': {'theme': 'dark', 'startup': 'EDIT'}, 'activeProject': 'first'})
    response = a.patch('/api/editor/preferences', json={'editor': {'theme': 'light'}, 'setupComplete': True})
    assert response.json()['editor'] == {'theme': 'light', 'startup': 'EDIT'}
    assert response.json()['activeProject'] == 'first'


def test_ticket_is_consumed_exactly_once_across_threads(guests):
    store.put('live_tickets', 'single-use', 'system', {'workspace': 'example'})
    with ThreadPoolExecutor(max_workers=8) as executor:
        rows = list(executor.map(lambda _: store.take('live_tickets', 'single-use', 'system'), range(16)))
    assert sum(row is not None for row in rows) == 1


def test_live_ticket_rejects_transport_override(guests):
    a, _ = guests
    response = a.post('/api/editor/live-ticket', json={'config': {'httpOptions': {'baseUrl': 'http://private'}}})
    assert response.status_code == 422


def test_provider_output_save_retry_does_not_repeat_generation(guests):
    a, b = guests
    workspace = a.get('/api/session').json()['workspace_id']
    payload = {'provider': 'replicate', 'url': 'https://api.replicate.com/v1/predictions', 'method': 'POST', 'body': '{}'}
    with patch('app.editor.jobs.threading.Thread'):
        job = a.post('/api/editor/jobs', json={'kind': 'provider', 'payload': payload, 'submission_key': 'paid-once'}).json()
    response = {'status': 200, 'content_type': 'application/json', 'text': json.dumps({'id': 'provider-42', 'status': 'succeeded', 'output': ['https://replicate.delivery/test.png']})}
    token = workspace_id.set(workspace)
    try:
        with patch('app.editor.jobs.proxy_request', return_value=response) as provider, \
             patch('app.editor.results.download_output', side_effect=ValueError('Storage interrupted.')):
            jobs._execute(job['id'], workspace, 'provider', payload, threading.Event())
        assert provider.call_count == 1
        failed = store.get('jobs', job['id'], workspace)
        assert failed['status'] == 'failed' and failed['retryable']
        assert failed['provider_id'] == 'provider-42'
        assert 'encrypted_result' not in jobs.public_job(failed)
        assert response['text'] not in json.dumps(failed)
        with patch('app.editor.jobs.proxy_request') as provider, \
             patch('app.editor.results.download_output', return_value=(b'owned output', 'image/png')):
            jobs._execute(job['id'], workspace, 'provider', payload, threading.Event())
        provider.assert_not_called()
        completed = store.get('jobs', job['id'], workspace)
        output = json.loads(completed['result']['text'])['output'][0]
        assert completed['status'] == 'completed'
        assert a.get(output).content == b'owned output'
        assert b.get(output).status_code == 404
        assert b.post('/api/editor/jobs/' + job['id'] + '/retry').status_code == 404
    finally:
        workspace_id.reset(token)


def test_ambiguous_provider_submission_cannot_be_retried(guests):
    a, _ = guests
    workspace = a.get('/api/session').json()['workspace_id']
    payload = {'provider': 'replicate', 'url': 'https://api.replicate.com/v1/predictions', 'method': 'POST'}
    with patch('app.editor.jobs.threading.Thread'):
        job = a.post('/api/editor/jobs', json={'kind': 'provider', 'payload': payload, 'submission_key': 'ambiguous'}).json()
    token = workspace_id.set(workspace)
    try:
        with patch('app.editor.jobs.proxy_request', return_value={'status': 504, 'content_type': 'application/json', 'text': '{}'}):
            jobs._execute(job['id'], workspace, 'provider', payload, threading.Event())
        row = store.get('jobs', job['id'], workspace)
        assert row['status'] == 'interrupted' and not row['retryable']
        assert a.post('/api/editor/jobs/' + job['id'] + '/retry').status_code == 422
    finally:
        workspace_id.reset(token)


def test_recorded_provider_operation_can_be_polled_after_restart_without_generation(guests):
    a, b = guests
    workspace = a.get('/api/session').json()['workspace_id']
    source = store.put('jobs', 'remote-generation', workspace, {'kind': 'provider', 'status': 'interrupted',
        'created': 1, 'provider': 'replicate', 'provider_id': 'remote-42', 'provider_status': 'processing',
        'poll_url': 'https://api.replicate.com/v1/predictions/remote-42', 'retryable': False})
    assert b.post('/api/editor/jobs/remote-generation/provider-status').status_code == 404
    with patch('app.editor.jobs.threading.Thread'):
        poll = a.post('/api/editor/jobs/remote-generation/provider-status').json()
    token = workspace_id.set(workspace)
    try:
        response = {'status': 200, 'content_type': 'application/json', 'text': json.dumps({'id': 'remote-42', 'status': 'succeeded', 'output': ['https://replicate.delivery/finished.png']})}
        with patch('app.editor.jobs.proxy_request', return_value=response) as request, patch('app.editor.results.download_output', return_value=(b'finished-image', 'image/png')):
            jobs._execute(poll['id'], workspace, 'provider-status', {'source_job_id': source['id']}, threading.Event())
        assert request.call_args.args == ('replicate', 'https://api.replicate.com/v1/predictions/remote-42')
        assert request.call_args.kwargs['method'] == 'GET'
        assert store.get('jobs', source['id'], workspace)['provider_status'] == 'succeeded'
        saved = store.get('jobs', poll['id'], workspace)
        assert saved['status'] == 'completed'
        result = json.loads(saved['result']['text'])['output'][0]
        assert a.get(result).content == b'finished-image'
        assert b.get(result).status_code == 404
        analytics = a.get('/api/analytics').json()
        assert next(job for job in analytics['recent_jobs'] if job['id'] == poll['id'])['output'] == result
    finally:
        workspace_id.reset(token)
