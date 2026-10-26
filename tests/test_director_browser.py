"""Browser interactions use the real editor, API, history and persistence.

Only paid provider responses are substituted; /ai/apply executes real commands.
Run with tests/run_browser_checks.py against isolated services.
"""
import io
import json
import os
import subprocess
import wave

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright, expect


@pytest.fixture
def studio():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(base_url=os.environ['RAYFLOW_TEST_URL'], viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('/#/studio')
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        yield page, context
        context.tracing.stop(path=str(__import__('pathlib').Path(os.environ['TEMP']) / ('director-' + __import__('uuid').uuid4().hex + '.zip')))
        assert not errors, errors
        context.close(); browser.close()


def media_and_captions(page):
    page.get_by_role('button', name='Skip for now').click()
    picture = io.BytesIO()
    Image.new('RGB', (320, 240), (20, 150, 70)).save(picture, format='PNG')
    page.locator('input[type=file][multiple]').set_input_files({'name': 'director-frame.png', 'mimeType': 'image/png', 'buffer': picture.getvalue()})
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    page.get_by_role('button', name='Captions', exact=True).click()
    captions = [dict(id='first', text='First caption', start_time=.1, end_time=2),
                dict(id='second', text='Second caption', start_time=2, end_time=3)]
    page.get_by_label('Import caption JSON', exact=True).set_input_files({'name': 'captions.json', 'mimeType': 'application/json',
        'buffer': json.dumps({'format': 'rayflow-captions-v1', 'subtitles': captions}).encode()})
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)


def saved_plan(page, context):
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
    expect(page.locator('.rayflow-studio')).to_have_count(0)
    session = context.request.get('/api/session').json()
    project = context.request.get('/api/editor/projects/' + session['preferences']['activeProject']).json()
    return next(s['document']['plan'] for s in project['sequences'] if s['kind'] == 'rayflow')


def test_provider_setup_update_switch_and_skip_persist(studio):
    page, context = studio
    expect(page.get_by_label('OpenAI GPT / Astra API key', exact=True)).to_be_visible()
    expect(page.get_by_label('Anthropic Claude Opus API key', exact=True)).to_be_visible()
    key = page.get_by_label('OpenAI GPT / Astra API key', exact=True)
    key.fill('browser-test-credential-not-real')
    expect(key).to_have_attribute('type', 'password')
    page.get_by_role('button', name='Show OpenAI GPT / Astra API key', exact=True).click()
    expect(key).to_have_attribute('type', 'text')
    page.get_by_role('button', name='Hide OpenAI GPT / Astra API key', exact=True).click()
    card = page.locator('.connection-grid > section').filter(has=key)
    page.route('**/api/editor/providers/openai/test', lambda route: route.fulfill(json={'ok': False, 'message': 'Credentials were rejected.'}))
    card.get_by_role('button', name='Test connection', exact=True).click()
    expect(page.get_by_text('Credentials were rejected.', exact=True)).to_be_visible()
    page.unroute('**/api/editor/providers/openai/test')
    page.route('**/api/editor/providers/openai/test', lambda route: route.fulfill(json={'ok': True, 'message': 'Key and model access verified.'}))
    card.get_by_role('button', name='Test connection', exact=True).click()
    expect(page.get_by_text('Key and model access verified.', exact=True)).to_be_visible()
    page.get_by_label('OpenAI GPT / Astra model', exact=True).select_option('gpt-4.1')
    card.get_by_role('button', name='Save', exact=True).click()
    expect(key).to_have_value('')
    page.get_by_role('button', name='Continue to Rayflow', exact=True).click()
    page.reload()
    expect(page.locator('.rayflow-setup-modal')).to_have_count(0)
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Connections', exact=True).click()
    expect(page.get_by_label('OpenAI GPT / Astra model', exact=True)).to_have_value('gpt-4.1')
    page.get_by_label('Studio AI director', exact=True).select_option('anthropic')
    page.get_by_role('button', name='Save preference', exact=True).click()
    expect(page.get_by_text('Director preference saved.', exact=True)).to_be_visible()
    assert context.request.get('/api/settings').json()['ai_provider'] == 'anthropic'
    card = page.locator('.connection-grid > section').filter(has=page.get_by_label('OpenAI GPT / Astra API key', exact=True))
    card.get_by_role('button', name='Remove key', exact=True).click()
    expect(card.get_by_text('No key saved', exact=True)).to_be_visible()
    assert 'browser-test-credential-not-real' not in page.evaluate('JSON.stringify(localStorage) + JSON.stringify(sessionStorage)')


def test_gemini_draft_test_model_dropdown_and_studio_selection(studio):
    page, context = studio
    key = page.get_by_label('Google Gemini API key', exact=True)
    card = page.locator('.connection-grid > section').filter(has=key)
    model = page.get_by_label('Google Gemini model', exact=True)
    expect(model).to_have_value('gemini-2.5-flash')
    key.fill('browser-gemini-draft-not-real')
    model.select_option('gemini-2.5-pro')
    calls = []
    def test_response(route):
        calls.append(route.request.post_data_json)
        route.fulfill(json={'ok': True, 'verified': True, 'message': 'Gemini key and selected model verified.'})
    page.route('**/api/editor/providers/gemini/test', test_response)
    card.get_by_role('button', name='Test connection', exact=True).click()
    expect(page.get_by_text('Gemini key and selected model verified.', exact=True)).to_be_visible()
    assert calls == [{'key': 'browser-gemini-draft-not-real', 'model': 'gemini-2.5-pro'}]
    assert not next(p for p in context.request.get('/api/editor/providers').json()['providers'] if p['id'] == 'gemini')['configured']
    card.get_by_role('button', name='Save', exact=True).click()
    expect(key).to_have_value('')
    assert context.request.get('/api/settings').json()['ai_provider'] == 'gemini'
    page.get_by_role('button', name='Continue to Rayflow', exact=True).click()
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Connections', exact=True).click()
    expect(page.get_by_label('Studio AI director', exact=True)).to_have_value('gemini')
    expect(model).to_have_value('gemini-2.5-pro')
    page.route('**/api/editor/providers/gemini/models', lambda route: route.fulfill(json={
        'models': ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-account-text-preview'],
    }))
    card.get_by_role('button', name='Find models', exact=True).click()
    expect(page.get_by_text('Found 3 models for Google Gemini. Choose a model and click Save.', exact=True)).to_be_visible()
    model.select_option('gemini-account-text-preview')
    card.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Google Gemini configuration saved.', exact=True)).to_be_visible()
    page.reload()
    expect(model).to_have_value('gemini-account-text-preview')
    model.select_option('__custom')
    page.get_by_label('Google Gemini custom model', exact=True).fill('gemini-custom-text')
    card.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Google Gemini configuration saved.', exact=True)).to_be_visible()
    settings = context.request.get('/api/settings').json()
    assert settings['gemini_model'] == 'gemini-custom-text' and settings['gemini_configured']
    assert 'browser-gemini-draft-not-real' not in page.evaluate('JSON.stringify(localStorage) + JSON.stringify(sessionStorage)')
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Studio', exact=True).click()
    expect(page.get_by_role('link', name='Google Gemini', exact=True)).to_be_visible()


def test_caption_delete_backspace_preview_multiselect_and_history(studio):
    page, context = studio
    media_and_captions(page)
    page.locator('[data-subtitle-id="first"]').click()
    page.keyboard.press('Delete')
    expect(page.locator('[data-subtitle-id]')).to_have_count(1)
    page.keyboard.press('Control+z')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    page.keyboard.press('Control+Shift+z')
    expect(page.locator('[data-subtitle-id]')).to_have_count(1)
    page.keyboard.press('Control+z')
    page.locator('[data-subtitle-id="first"]').click()
    preview = page.get_by_role('button', name='Select preview caption: First caption', exact=True)
    expect(preview).to_be_visible()
    preview.click()
    page.keyboard.press('Backspace')
    expect(page.locator('[data-subtitle-id]')).to_have_count(1)
    expect(preview).to_have_count(0)
    page.keyboard.press('Control+z')
    text = page.get_by_label('Caption text', exact=True).first
    text.fill('Text remains editable')
    text.press('Backspace')
    text.press('Delete')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    page.get_by_label('Edit direction', exact=True).fill('Typing here also stays safe')
    page.get_by_label('Edit direction', exact=True).press('Backspace')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    page.locator('[data-subtitle-id="first"]').click()
    page.get_by_label('Caption start', exact=True).first.press('Delete')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    page.evaluate("""() => {
        const editor = document.createElement('div'); editor.contentEditable = 'true';
        editor.dataset.testEditor = 'true'; editor.innerHTML = '<span>Nested editable text</span>';
        document.querySelector('[data-caption-card="first"]').append(editor);
    }""")
    page.locator('[data-test-editor] span').click()
    page.keyboard.press('Backspace'); page.keyboard.press('Delete')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    page.evaluate("document.querySelector('[data-test-editor]').remove()")
    page.locator('[data-subtitle-id="first"]').click()
    page.locator('[data-subtitle-id="second"]').click(modifiers=['Control'])
    page.keyboard.press('Delete')
    expect(page.locator('[data-subtitle-id]')).to_have_count(0)
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    page.keyboard.press('Delete')  # no selection must not delete a clip
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    page.keyboard.press('Control+z')
    page.locator('[data-caption-card="first"]').get_by_title('Delete caption', exact=True).click()
    expect(page.locator('[data-subtitle-id]')).to_have_count(1)
    assert [s['id'] for s in saved_plan(page, context)['subtitles']] == ['second']


def test_director_real_apply_followup_failure_and_panel_dismissal(studio):
    page, context = studio
    media_and_captions(page)
    close = page.get_by_role('button', name='Close Try AI Direction panel', exact=True)
    close.focus(); page.keyboard.press('Enter')
    expect(page.get_by_role('region', name='Try AI Direction', exact=True)).to_have_count(0)
    page.get_by_role('button', name='1:1', exact=True).click()
    expect(close).to_have_count(0)
    requests = []
    plans = [
        [('remove_subtitles', {'all': True}), ('set_aspect_ratio', {'aspect_ratio': '16:9'})],
        [('generate_subtitles', {'all': True}), ('style_subtitles', {'all': True, 'style': {'font_size': 36}})],
        [('delete_clip', {'clip_id': 'does-not-exist'})],
        [('undo', {})],
        [('redo', {})],
    ]
    def model(route):
        body = route.request.post_data_json
        requests.append(body)
        actions = [{'type': name, 'params': params} for name, params in plans.pop(0)]
        route.fulfill(json={'explanation': 'Review these changes', 'actions': actions,
            'clarification': None, 'proposed_plan': body['current_plan'], 'applied_changes': ['Caption change', 'Format change']})
    page.route('**/api/ai/plan', model)
    direction = page.get_by_label('Edit direction', exact=True)
    def submit(words):
        direction.fill(words)
        page.get_by_role('button', name='Send edit direction', exact=True).click()
        page.get_by_role('button', name='Approve and apply', exact=True).click()
        expect(page.get_by_role('dialog', name='Review your Rayflow edit', exact=True)).to_have_count(0)
    submit('Take the captions off and make this landscape')
    expect(page.locator('[data-subtitle-id]')).to_have_count(0)
    submit('Actually keep the subtitles but make them smaller')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    assert any('Removed 2 caption' in turn['content'] for turn in requests[1]['conversation'])
    assert requests[1]['current_plan']['aspect_ratio'] == '16:9'
    submit('Remove the missing clip')
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    expect(page.get_by_text('The requested clip does not exist in the active project.', exact=False).first).to_be_visible()
    submit('Undo that change')
    expect(page.locator('[data-subtitle-id]')).to_have_count(0)
    submit('Redo it please')
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    result = saved_plan(page, context)
    assert result['aspect_ratio'] == '16:9' and all(s['style']['font_size'] == 36 for s in result['subtitles'])
    page.get_by_role('navigation', name='Main').get_by_role('link', name='Studio', exact=True).click()
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    expect(page.get_by_role('region', name='Try AI Direction', exact=True)).to_have_count(0)


def test_clip_and_audio_keyboard_deletion_are_undoable(studio, tmp_path):
    page, _ = studio
    media_and_captions(page)
    from imageio_ffmpeg import get_ffmpeg_exe
    video = tmp_path / 'director-video.mp4'
    subprocess.run([get_ffmpeg_exe(), '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:r=10:d=2', '-pix_fmt', 'yuv420p', str(video)],
                   check=True, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    page.get_by_role('button', name='Media (1)', exact=True).click()
    page.locator('input[type=file][multiple]').set_input_files(str(video))
    expect(page.locator('[data-clip-id]')).to_have_count(2)
    page.locator('[data-clip-id]').last.click()
    page.keyboard.press('Delete')
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    page.keyboard.press('Control+z')
    expect(page.locator('[data-clip-id]')).to_have_count(2)
    page.keyboard.press('Control+Shift+z')
    expect(page.locator('[data-clip-id]')).to_have_count(1)
    page.get_by_role('button', name='Music', exact=True).click()
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b'\0\0' * 32000)
    page.locator('input[type=file][accept="audio/*"]').set_input_files({'name': 'test-silence.wav', 'mimeType': 'audio/wav', 'buffer': buffer.getvalue()})
    track = page.get_by_role('button', name='Select audio track', exact=True)
    expect(track).to_be_visible(timeout=120000)
    track.click(); page.keyboard.press('Backspace')
    expect(track).to_have_count(0)
    page.keyboard.press('Control+z')
    expect(track).to_be_visible()
    page.keyboard.press('Control+Shift+z')
    expect(track).to_have_count(0)
    expect(page.locator('[data-clip-id]')).to_have_count(1)


def test_missing_provider_stale_proposal_and_mobile_dismissal(studio):
    page, _ = studio
    media_and_captions(page)
    page.set_viewport_size({'width': 600, 'height': 900})
    page.get_by_role('button', name='Director', exact=True).click()
    page.get_by_role('button', name='Close Try AI Direction panel', exact=True).click()
    direction = page.get_by_label('Edit direction', exact=True)
    direction.fill('Please remove all subtitles')
    page.get_by_role('button', name='Send edit direction', exact=True).click()
    expect(page.get_by_text('Connect OpenAI, Anthropic, or OpenRouter in Connections', exact=False).first).to_be_visible()
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    held = []
    page.route('**/api/ai/plan', lambda route: held.append(route))
    direction.fill('Remove all captions')
    with page.expect_request('**/api/ai/plan'):
        page.get_by_role('button', name='Send edit direction', exact=True).click()
    page.get_by_role('button', name='1:1', exact=True).click()
    held[0].fulfill(json={'explanation': 'Remove captions', 'actions': [{'type': 'remove_subtitles', 'params': {'all': True}}],
        'clarification': None, 'proposed_plan': held[0].request.post_data_json['current_plan'], 'applied_changes': ['Remove captions']})
    expect(page.get_by_text('The project changed while planning.', exact=False).first).to_be_visible()
    expect(page.get_by_role('dialog', name='Review your Rayflow edit', exact=True)).to_have_count(0)
    expect(page.locator('[data-subtitle-id]')).to_have_count(2)
