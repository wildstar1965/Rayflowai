"""Fake recognition supplies speech events; real editor actions and saves run."""
import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright, expect

SPEECH = """() => {
  window.SpeechRecognition = class {
    constructor() { window.testSpeech = this; }
    start() { this.onstart?.(); this.onspeechstart?.(); }
    stop() { this.onend?.(); }
    abort() { this.onend?.(); }
    words(text, final) { const result = Object.assign([{transcript:text}], {isFinal:final}); this.onresult?.({results:[result]}); }
  };
}"""


@pytest.fixture
def browser_page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(base_url=os.environ['RAYFLOW_TEST_URL'], viewport={'width': 1600, 'height': 1100})
        page = context.new_page()
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('(' + SPEECH + ')()')
        yield page, context
        assert not errors, errors
        context.close()
        browser.close()


def test_studio_voice_only_submits_final_speech_and_can_undo(browser_page, tmp_path):
    page, context = browser_page
    page.goto('/#/studio')
    page.get_by_role('button', name='Skip for now').click()
    page.evaluate(SPEECH)
    image = io.BytesIO()
    Image.new('RGB', (64, 64), 'green').save(image, format='PNG')
    page.locator('input[type=file][multiple]').set_input_files({'name': 'voice.png', 'mimeType': 'image/png', 'buffer': image.getvalue()})
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    page.locator('[data-clip-id]').click()
    context.request.put('/api/settings', data={'values': {'AI_PROVIDER': 'agentrouter'}})
    submissions = []
    def proposal(route):
        body = route.request.post_data_json
        submissions.append(body)
        route.fulfill(json={'explanation': 'Rotate clockwise and move right', 'applied_changes': ['Rotate 90 degrees and move right 5%.'], 'proposed_plan': body['current_plan'], 'actions': [{'type': 'transform_clip',
            'params': {'clip_id': body['context']['selected_clip_id'], 'rotation': 90, 'offset_x': .05, 'relative': True}}]})
    page.route('**/api/ai/plan', proposal)
    page.get_by_role('button', name='Start voice instruction', exact=True).click()
    page.evaluate("window.testSpeech.onerror({error:'not-allowed'}); window.testSpeech.stop()")
    expect(page.get_by_text('Microphone access was denied. Allow microphone access in your browser and try again.', exact=True)).to_be_visible()
    assert not submissions
    page.get_by_role('button', name='Start voice instruction', exact=True).click()
    expect(page.locator('.rayflow-voice-wave')).to_be_visible()
    assert page.locator('.rayflow-voice-wave i').first.evaluate('node => getComputedStyle(node).animationName') == 'rayflow-voice-wave'
    page.evaluate("window.testSpeech.words('Rotate the selected clip', false)")
    expect(page.get_by_label('Edit direction', exact=True)).to_have_value('Rotate the selected clip')
    assert not submissions
    page.screenshot(path=str(tmp_path / 'voice-waveform.png'))
    page.evaluate("window.testSpeech.words('Rotate selected clip clockwise 90 degrees and move right', true); window.testSpeech.stop()")
    page.get_by_role('button', name='Approve and apply', exact=True).click()
    expect(page.locator('.rayflow-voice-wave')).to_have_count(0)
    assert len(submissions) == 1
    expect(page.get_by_role('button', name='Approve and apply', exact=True)).to_have_count(0)
    page.get_by_title('Undo (Ctrl+Z)', exact=True).click()
    page.keyboard.press('Control+Shift+z')
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
    session = context.request.get('/api/session').json()
    project = context.request.get('/api/editor/projects/' + session['preferences']['activeProject']).json()
    plan = next(s['document']['plan'] for s in project['sequences'] if s['kind'] == 'rayflow')
    assert plan['clips'][0]['rotation'] == 90 and plan['clips'][0]['offset_x'] == .05


@pytest.mark.parametrize('provider', ['agentrouter', 'ollama'])
def test_editor_voice_tool_moves_and_rotates_selected_clip(browser_page, provider, tmp_path):
    page, context = browser_page
    page.goto('/#/editor')
    page.get_by_role('button', name='Skip for now').click()
    page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
    page.evaluate(SPEECH)
    page.get_by_role('navigation', name='Main').get_by_role('button', name='Assets', exact=True).click()
    media = io.BytesIO()
    Image.new('RGB', (64, 64), 'green').save(media, format='PNG')
    page.get_by_role('dialog').locator('input[type=file]').set_input_files({'name': 'voice-editor.png', 'mimeType': 'image/png', 'buffer': media.getvalue()})
    page.get_by_role('button', name='Use in current workspace').click()
    page.locator('.rayflow-editor [draggable=true]').filter(has=page.get_by_text('voice-editor.png', exact=True)).first.click()
    expect(page.locator('.rayflow-editor .tl-clip')).to_have_count(1)
    page.locator('.rayflow-editor .tl-clip').click()
    context.request.put('/api/settings', data={'values': {'AI_PROVIDER': provider}})
    settings = context.request.get('/api/settings').json()
    page.route('**/api/settings', lambda route: route.fulfill(json={**settings, 'agentrouter_configured': True}))
    page.route('**/api/ollama/status', lambda route: route.fulfill(json={'ready': True, 'default_model': 'qwen3:8b', 'host': 'http://127.0.0.1:11434'}))
    calls = []
    def jobs(route):
        data = route.request.post_data_json
        if data.get('kind') != 'provider':
            route.continue_(); return
        payload = json.loads(data['payload']['body'])
        calls.append(payload)
        message = {'role': 'assistant', 'content': 'Moved and rotated the selected clip.'}
        if len(calls) == 1:
            message['tool_calls'] = [
                {'id': 'rotate-1', 'type': 'function', 'function': {'name': 'rotateSelectedClip', 'arguments': json.dumps({'degrees': 90})}},
                {'id': 'move-1', 'type': 'function', 'function': {'name': 'moveSelectedClip', 'arguments': json.dumps({'direction': 'right', 'percent': 5})}},
            ]
        if provider == 'ollama':
            for call in message.get('tool_calls', []):
                call['function']['arguments'] = json.loads(call['function']['arguments'])
            body = {'done': True, 'done_reason': 'stop', 'message': message}
        else:
            body = {'choices': [{'finish_reason': 'stop', 'message': message}]}
        result = {'status': 200, 'content_type': 'application/json', 'text': json.dumps(body)}
        def finished(route):
            route.fulfill(json={'status': 'completed', 'result': result})
        page.route('**/api/editor/jobs/voice-chat-' + str(len(calls)), finished)
        route.fulfill(json={'id': 'voice-chat-' + str(len(calls)), 'status': 'completed', 'result': result})
    page.route('**/api/editor/jobs', jobs)
    page.get_by_role('tablist', name='Inspector sections').get_by_role('tab', name='Assistant', exact=True).click()
    page.get_by_role('button', name='Start voice instruction', exact=True).click()
    page.evaluate("window.testSpeech.words('Rotate selected clip 90 degrees and move right a little', true); window.testSpeech.stop()")
    expect(page.get_by_text('Moved and rotated the selected clip.', exact=True)).to_be_visible(timeout=15000)
    assert len(calls) == 2
    assert any(tool['function']['name'] == 'moveSelectedClip' for tool in calls[0]['tools'])
    if provider == 'ollama':
        assert calls[0]['think'] is False and calls[0]['options']['num_ctx'] == 8192
        assert calls[1]['messages'][-1]['tool_name'] == 'moveSelectedClip'
        (tmp_path / 'ollama-chat-request.json').write_text(json.dumps(calls[0]), encoding='utf-8')
    project_id = context.request.get('/api/session').json()['preferences']['activeProject']
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Studio', exact=True).click()
    expect(page.locator('.rayflow-editor')).to_have_count(0)
    project = context.request.get('/api/editor/projects/' + project_id).json()
    transform = project['project']['timelineClips'][0]['transform']
    assert transform['rotation'] == 90 and transform['position'] == {'x': 55, 'y': 50}
