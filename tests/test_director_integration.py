"""Director contracts, provider transport and real transactional editing (no paid calls)."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app
from app.schemas.ai_editing import AIAction, AIEditingPlan, EditorContext, ConversationTurn
from app.schemas.editing_plan import EditingPlan
from app.services import ai_provider, ai_editing
from app.editor.store import store


def project():
    return EditingPlan.model_validate({
        'duration_seconds': 8,
        'clips': [dict(id='a', image_url='a.mp4', start_time=0, duration=4, media_type='video', source_duration=4),
                  dict(id='b', image_url='b.mp4', start_time=4, duration=4, media_type='video', source_duration=4)],
        'subtitles': [dict(id='caption-a', text='Keep this correction', start_time=1, end_time=3, source_clip_id='a',
                           words=[dict(word='Keep', start=1, end=2)]),
                      dict(id='caption-b', text='Second caption', start_time=5, end_time=7, source_clip_id='b')],
    })


def proposal(*actions):
    return AIEditingPlan(explanation='Proposed edit', actions=[AIAction(type=name, params=params) for name, params in actions])


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    a, b = TestClient(app), TestClient(app)
    assert a.post('/api/session').status_code == b.post('/api/session').status_code == 200
    return a, b


@pytest.mark.parametrize('provider,model', [('openai', 'gpt-6-astra'), ('anthropic', 'claude-opus-5-5')])
def test_provider_save_test_switch_delete_is_private(clients, monkeypatch, provider, model):
    a, b = clients
    secret = 'unit-test-credential-never-real'
    endpoint = '/api/editor/providers/' + provider
    assert a.put(endpoint, json={'key': secret, 'model': model}).status_code == 200
    assert a.put('/api/settings', json={'values': {'AI_PROVIDER': provider}}).status_code == 200
    assert a.get('/api/settings').json()['ai_provider'] == provider
    identity = a.get('/api/session').json()['workspace_id']
    assert secret not in json.dumps(store.get('credentials', identity + ':' + provider, identity))
    assert secret not in a.get('/api/editor/providers').text
    assert not next(row for row in b.get('/api/editor/providers').json()['providers'] if row['id'] == provider)['configured']
    remote = Mock(return_value=Mock(status_code=200, json=lambda: {'id': model}))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    assert a.post(endpoint + '/test', json={'model': model}).json()['verified']
    assert remote.call_args.args[1].startswith('https://api.')
    assert remote.call_args.kwargs['allow_redirects'] is False
    assert next(row for row in a.get('/api/editor/providers').json()['providers'] if row['id'] == provider)['tested']
    assert a.delete(endpoint).status_code == 200
    assert not a.post(endpoint + '/test').json()['ok']


def test_draft_key_test_does_not_save_and_invalid_input_does_not_echo_secrets(clients, monkeypatch):
    a, _ = clients
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(return_value=Mock(status_code=401)))
    secret = 'draft-test-key'
    result = a.post('/api/editor/providers/openai/test', json={'key': secret, 'model': 'gpt-6-astra'})
    assert not result.json()['ok'] and 'rejected' in result.json()['message']
    assert secret not in result.text
    result = a.put('/api/editor/providers/openai', json={'key': {'nested': secret}})
    assert result.status_code == 422 and secret not in result.text
    result = a.put('/api/editor/providers/openai', json={'key': secret, 'model': 'invented-model'})
    assert result.status_code == 422 and secret not in result.text
    assert not next(p for p in a.get('/api/editor/providers').json()['providers'] if p['id'] == 'openai')['configured']
    assert a.put('/api/editor/providers/openai', headers={'origin': 'https://untrusted.invalid'}, json={'key': secret}).status_code == 403
    assert TestClient(app).put('/api/editor/providers/openai', json={'key': secret}).status_code == 401


@pytest.mark.parametrize('status,message', [(401, 'Credentials'), (403, 'Credentials'), (429, 'limit'), (404, 'unavailable'), (500, 'unavailable')])
def test_provider_errors_are_useful_and_redacted(monkeypatch, status, message):
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(return_value=Mock(status_code=status, text='secret-key')))
    result = ai_provider.test_connection('openai', 'secret-key', 'gpt-6-astra')
    assert not result['ok'] and message in result['message'] and 'secret-key' not in result['message']


@pytest.mark.parametrize('error,message', [(requests.Timeout, 'timed out'), (requests.ConnectionError, 'network')])
def test_network_errors(monkeypatch, error, message):
    monkeypatch.setattr(ai_provider.requests, 'request', Mock(side_effect=error('secret-key')))
    result = ai_provider.test_connection('anthropic', 'secret-key', 'claude-opus-5-5')
    assert not result['ok'] and message in result['message'] and 'secret-key' not in result['message']


@pytest.mark.parametrize('provider', ['openai', 'anthropic'])
def test_shared_provider_transport_parses_real_api_response_shape(monkeypatch, provider):
    values = {'AI_PROVIDER': provider, provider.upper() + '_API_KEY': 'test-key'}
    monkeypatch.setattr(ai_provider, 'setting', lambda key, default='': values.get(key, default))
    payload = {'explanation': 'Remove the selected captions', 'actions': [{'type': 'remove_subtitles', 'params': {'clip_id': 'a'}}]}
    body = {'content': [{'type': 'text', 'text': json.dumps(payload)}], 'stop_reason': 'end_turn'} if provider == 'anthropic' else {
        'choices': [{'message': {'content': json.dumps(payload)}, 'finish_reason': 'stop'}]}
    remote = Mock(return_value=Mock(status_code=200, json=lambda: body))
    monkeypatch.setattr(ai_provider.requests, 'request', remote)
    plan = ai_editing.request_plan('Take the captions off this clip', project())
    edited, _ = ai_editing.apply_actions(project(), plan)
    assert [s.id for s in edited.subtitles] == ['caption-b']
    assert 'test-key' not in json.dumps(remote.call_args.kwargs['json'])


@pytest.mark.parametrize('words', ['Take the subtitles off', 'Get rid of the captions', 'Remove the text from the selected clip'])
def test_language_reaches_model_with_selection_and_followup_context(monkeypatch, words):
    def model(messages):
        data = json.loads(messages[1]['content'])
        assert data['command'] == words
        assert data['editor_context']['selected_clip_id'] == 'a'
        assert data['current_plan']['subtitles'][0]['text'] == 'Keep this correction'
        assert data['conversation'][0]['content'] == 'Please edit my first clip'
        return proposal(('remove_subtitles', {'clip_id': 'a'})).model_dump()
    monkeypatch.setattr(ai_editing, 'generate_plan', model)
    result = ai_editing.request_plan(words, project(), EditorContext(selected_clip_id='a'),
                                    [ConversationTurn(role='user', content='Please edit my first clip')])
    edited, _ = ai_editing.apply_actions(project(), result)
    assert [s.id for s in edited.subtitles] == ['caption-b']


def test_remove_restore_style_and_move_keep_actual_attachments():
    original = project()
    removed, _ = ai_editing.apply_actions(original, proposal(('remove_subtitles', {'clip_id': 'a'})))
    restored, changes = ai_editing.apply_actions(removed, proposal(
        ('generate_subtitles', {'clip_id': 'a'}), ('style_subtitles', {'clip_id': 'a', 'style': {'font_size': 36}}),
        ('move_clip', {'clip_id': 'a', 'index': 1})))
    caption = next(s for s in restored.subtitles if s.id == 'caption-a')
    assert caption.text == 'Keep this correction' and caption.style.font_size == 36
    assert caption.start_time == 5 and caption.words[0].start == 5
    assert restored.clips[0].id == 'b' and len(changes) == 3
    assert len(original.subtitles) == 2 and original.subtitles[0].style is None


def test_failed_batch_does_not_publish_partial_changes():
    original = project()
    before = original.model_dump()
    with pytest.raises(ai_editing.AIEditingError):
        ai_editing.apply_actions(original, proposal(('remove_subtitles', {'all': True}), ('delete_clip', {'clip_id': 'missing'})))
    assert original.model_dump() == before


def test_split_duplicates_and_clips_caption_and_transcript():
    original = project()
    original.transcript = copy.deepcopy(original.subtitles)
    split, _ = ai_editing.apply_actions(original, proposal(('split_clip', {'clip_id': 'a', 'timestamp': 2})))
    first, second = split.clips[:2]
    for collection in (split.subtitles, split.transcript):
        assert next(s for s in collection if s.source_clip_id == first.id).end_time == 2
        assert next(s for s in collection if s.source_clip_id == second.id).start_time == 2


@pytest.mark.parametrize('action', [
    ('shell', {'command': 'anything'}), ('remove_subtitles', {}), ('remove_subtitles', {'all': True, 'clip_id': 'a'}),
    ('style_subtitles', {'all': True, 'style': {'font_size': 10000}}),
    ('style_subtitles', {'all': True, 'style': {'unsupported': True}}), ('set_clip_volume', {'clip_id': 'a', 'volume': float('nan')}),
    ('move_clip', {'clip_id': 'a', 'index': -1}), ('delete_clip', {'clip_id': 'a', 'code': 'anything'})])
def test_action_schema_rejects_unsafe_or_invalid_arguments(action):
    with pytest.raises(ValueError): proposal(action)


def test_api_plan_review_apply_and_unsupported_feedback(clients, monkeypatch):
    a, _ = clients
    monkeypatch.setattr(ai_editing, 'generate_plan', lambda _: proposal(('remove_subtitles', {'all': True})).model_dump())
    response = a.post('/api/ai/plan', json={'command': 'Please remove the captions', 'current_plan': project().model_dump()})
    assert response.status_code == 200
    reviewed = response.json()
    applied = a.post('/api/ai/apply', json={'current_plan': project().model_dump(),
        'ai_plan': {key: reviewed[key] for key in ('explanation', 'actions', 'clarification')}})
    assert applied.status_code == 200 and not applied.json()['proposed_plan']['subtitles']
    monkeypatch.setattr(ai_editing, 'generate_plan', lambda _: {'explanation': 'Choose which text you mean.', 'clarification': 'Captions or title?', 'actions': []})
    response = a.post('/api/ai/plan', json={'command': 'Remove that text', 'current_plan': project().model_dump()})
    assert response.status_code == 200 and response.json()['clarification'] == 'Captions or title?'
    assert len(response.json()['proposed_plan']['subtitles']) == 2


def test_silence_removal_uses_measured_audio_and_retains_source_ranges(monkeypatch, tmp_path):
    import wave
    import numpy as np
    from app.services import director_silence, media, speech_transcription
    rate = 16000
    samples = np.sin(2 * np.pi * 200 * np.arange(rate * 4) / rate) * 8000
    samples[rate:rate*3] = 0
    def extract(source, output):
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes(samples.astype('<i2').tobytes())
    monkeypatch.setattr(media, 'uploaded_path', lambda _: tmp_path / 'owned.mp4')
    monkeypatch.setattr(speech_transcription, 'extract_audio_from_media', extract)
    result, changes = ai_editing.apply_actions(project(), proposal(('remove_silence', {'clip_id': 'a'})))
    assert len(result.clips) == 3 and result.duration_seconds < 7
    assert result.clips[1].source_start > 2.8 and result.clips[2].id == 'b'
    assert 'measured silence' in changes[0]
