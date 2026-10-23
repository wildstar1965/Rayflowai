"""Windows caption acceptance checks using real local Whisper, HTTP and Edge.

Requires cached Medium model, System.Speech and the existing test dependencies.
Servers use spare ports; all media is generated specifically for these tests.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from test_studio_browser import ROOT, KEY, local_servers, plan, wait_plan

sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import FFMPEG_PATH, UPLOAD_DIR


@pytest.fixture(scope='module')
def speech_video(tmp_path_factory):
    directory = tmp_path_factory.mktemp('caption-speech')
    wav, video = directory / 'speech.wav', directory / 'speech.mp4'
    command = """Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SetOutputToWaveFile($env:RAYFLOW_TEST_SPEECH_PATH)
    $speaker.Speak('Today we are testing captions. Clear words make every video easier to follow.')
} finally { $speaker.Dispose() }
"""
    fixture = os.getenv('RAYFLOW_TEST_SPEECH_FIXTURE')
    if fixture:
        shutil.copyfile(fixture, wav)
    else:
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                       env={**{key: value for key, value in os.environ.items()
                               if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP',
                                                  'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'COMSPEC'}},
                            'RAYFLOW_TEST_SPEECH_PATH': str(wav)},
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=c=0x263044:s=640x360:r=30', '-i', str(wav),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    '-shortest', str(video)], check=True, capture_output=True)
    return video


@pytest.fixture
def captions(local_servers, speech_video):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(base_url=local_servers, viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(20000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(local_servers + '/#/studio')
        page.locator('input[type=file][multiple]').set_input_files(str(speech_video))
        wait_plan(page, 'p.clips.length === 1')
        page.get_by_role('button', name='16:9', exact=True).click()
        page.get_by_role('button', name='Captions', exact=False).click()
        try:
            yield page, errors
        finally:
            context.close()
            browser.close()


def import_json(page, data):
    page.get_by_label('Import caption JSON', exact=True).set_input_files({
        'name': 'captions.json', 'mimeType': 'application/json',
        'buffer': json.dumps(data, ensure_ascii=False).encode('utf8'),
    })


def test_real_speech_edits_regeneration_downloads_and_reload(captions, tmp_path):
    page, errors = captions
    temporary_before = set(UPLOAD_DIR.glob('temp_*.wav'))
    model = page.get_by_label('Caption transcription model')
    expect(model).to_have_value('medium', timeout=120000)
    assert model.locator('option[value="tiny"], option[value="base"]').count() == 0
    assert model.locator('option[value="large-v3"]').evaluate('option => option.disabled')
    page.get_by_label('Transcription language').fill('en')
    generate = page.get_by_role('button', name='Generate speech captions', exact=True)
    generate.click()
    page.wait_for_function(f"JSON.parse(localStorage.getItem('{KEY}'))?.plan?.subtitles?.length > 0", timeout=120000)
    generated = plan(page)
    assert any(s['words'] for s in generated['subtitles'])
    assert 'caption' in ' '.join(s['text'] for s in generated['subtitles']).lower()
    previous = 0
    for sub in generated['subtitles']:
        assert previous <= sub['start_time'] < sub['end_time'] <= generated['duration_seconds']
        previous = sub['end_time']
        for word in sub['words']:
            assert sub['start_time'] <= word['start'] < word['end'] <= sub['end_time']
    assert set(UPLOAD_DIR.glob('temp_*.wav')) == temporary_before

    editor = page.get_by_label('Caption text', exact=True).first
    editor.fill('A manual correction survives regeneration.')
    editor.press('Tab')
    wait_plan(page, "p.subtitles[0].text === 'A manual correction survives regeneration.'")
    manual = plan(page)['subtitles'][0]
    with page.expect_response(re.compile(r'/api/transcribe$')):
        generate.click()
    expect(generate).to_be_enabled(timeout=120000)
    assert plan(page)['subtitles'][0] == manual

    document = None
    for fmt in ['srt', 'vtt', 'ass', 'json']:
        page.get_by_label('Subtitle export format').select_option(fmt)
        with page.expect_download() as pending:
            page.get_by_role('button', name='Download captions', exact=True).click()
        download = pending.value
        assert download.suggested_filename == f'rayflow-captions.{fmt}'
        destination = tmp_path / download.suggested_filename
        download.save_as(destination)
        text = destination.read_text(encoding='utf8')
        assert manual['text'] in text
        if fmt == 'json':
            document = json.loads(text)
        elif fmt == 'ass':
            assert '[Events]' in text and 'Dialogue:' in text
        else:
            assert ' --> ' in text
            assert text.startswith('WEBVTT') == (fmt == 'vtt')

    import_json(page, document)
    expect(page.get_by_text('Captions imported. Undo restores the previous captions.', exact=True)).to_be_visible()
    assert plan(page)['subtitles'] == document['subtitles']
    page.reload()
    expect(page.get_by_role('slider', name='Timeline playhead')).to_be_visible()
    assert plan(page)['subtitles'] == document['subtitles']
    head = page.get_by_role('slider', name='Timeline playhead')
    page.get_by_role('button', name='Play', exact=True).click()
    page.wait_for_function("Number(document.querySelector('[aria-label=\"Timeline playhead\"]').getAttribute('aria-valuenow')) > 0.3")
    page.get_by_role('button', name='Pause', exact=True).click()
    assert float(head.get_attribute('aria-valuenow')) > .3
    assert errors == []


def test_engine_import_romanization_errors_and_preview_export(captions, tmp_path):
    page, errors = captions
    transcript = {'duration': 3, 'hasWordTimings': True, 'language': 'hi', 'words': [
        {'text': 'आज', 'roman': 'aaj', 'start': .2, 'end': .6, 'speakerId': 'speaker_1'},
        {'text': 'meeting', 'start': .7, 'end': 1.1, 'speakerId': 'speaker_1'},
        {'text': 'है।', 'roman': 'hai.', 'start': 1.2, 'end': 1.6, 'speakerId': 'speaker_1'},
        {'text': 'ಇದು', 'start': 2, 'end': 2.3, 'speakerId': 'speaker_2'},
    ]}
    import_json(page, transcript)
    wait_plan(page, "p.subtitles?.[0]?.text === 'आज meeting है।'")
    native = plan(page)['subtitles']
    assert native[0]['words'][0]['speaker_id'] == 'speaker_1'
    assert native[0]['words'][0]['start'] == .2
    page.get_by_role('button', name='Romanize captions', exact=True).click()
    wait_plan(page, "p.subtitles[0].text === 'aaj meeting hai.' && p.subtitles[1].text === 'idu'")
    assert plan(page)['subtitles'][0]['words'][0]['start'] == .2
    page.keyboard.press('Control+z')
    wait_plan(page, "p.subtitles[0].text === 'आज meeting है।'")
    assert plan(page)['subtitles'] == native

    import_json(page, {**transcript, 'hasWordTimings': False})
    expect(page.get_by_text('This transcript has no genuine word timestamps. Import a word-timed transcript.', exact=True)).to_be_visible()
    assert plan(page)['subtitles'] == native
    for width, height in [(1440, 900), (768, 600), (390, 650)]:
        page.set_viewport_size({'width': width, 'height': height})
        if width < 1024 and not page.get_by_role('button', name='Close media', exact=True).is_visible():
            page.get_by_role('button', name='Media', exact=True).click()
        page.get_by_role('button', name='Download captions', exact=True).scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.set_viewport_size({'width': 1440, 'height': 900})

    # Render the same native-script plan and compare decoded frames to the canvas.
    current = plan(page)
    preview_response = page.request.post('/api/cinematic/captions', data=current)
    assert preview_response.ok
    events = preview_response.json()
    source = current['source_filename']
    result = page.request.post('/api/render', data={'plan': current, 'image_filenames': [source]})
    assert result.ok, result.text()
    job = result.json()['job_id']
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = page.request.get(f'/api/render/{job}').json()
        if status['status'] in ('completed', 'failed'):
            break
        page.wait_for_timeout(250)
    assert status['status'] == 'completed', status
    response = page.request.get(f'/api/render/{job}/download')
    assert response.ok
    exported = tmp_path / 'native-captions.mp4'
    exported.write_bytes(response.body())
    head = page.get_by_role('slider', name='Timeline playhead')
    comparisons = []
    artifacts = ROOT / 'test_artifacts' / 'caption-engine'
    artifacts.mkdir(exist_ok=True)
    for second in [1, 2, 3]:
        head.focus()
        head.press('Home')
        for _ in range(second):
            head.press('Shift+ArrowRight')
        page.wait_for_timeout(1000)
        data = page.locator('main canvas').evaluate('c => ({width:c.width,height:c.height,png:c.toDataURL()})')
        preview = np.asarray(Image.open(io.BytesIO(base64.b64decode(data['png'].split(',')[1]))).convert('RGB')).astype(float)
        raw = subprocess.check_output([FFMPEG_PATH, '-v', 'error', '-ss', str(second), '-i', str(exported),
            '-frames:v', '1', '-vf', f"scale={data['width']}:{data['height']}", '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        rendered = np.frombuffer(raw, np.uint8).reshape(data['height'], data['width'], 3).astype(float)
        difference = float(np.abs(preview - rendered).mean())
        comparison = {'second': second, 'mean_rgb_error': difference}
        event = next((event for event in events if event['start_time'] <= second < event['end_time']), None)
        if event:
            raster_response = page.request.get(event['url'])
            assert raster_response.ok
            raster = np.asarray(Image.open(io.BytesIO(raster_response.body())).convert('RGBA')
                                .resize((data['width'], data['height'])))
            glyphs = (raster[:, :, 3] > 200) & (raster[:, :, :3].max(axis=2) > 150)
            assert glyphs.sum() > 20
            assert preview[glyphs].max(axis=1).mean() > 100
            assert rendered[glyphs].max(axis=1).mean() > 100
            comparison['caption_rgb_error'] = float(np.abs(preview[glyphs] - rendered[glyphs]).mean())
            assert comparison['caption_rgb_error'] < 18, comparison
            Image.fromarray(preview.astype(np.uint8)).save(artifacts / f'preview-{second}s.png')
        comparisons.append(comparison)
        assert difference < 12, comparisons
    (artifacts / 'preview-export.json').write_text(json.dumps(comparisons, indent=2), encoding='utf8')
    # Verify the original speech audio is still present after burned-in export.
    pcm = subprocess.check_output([FFMPEG_PATH, '-v', 'error', '-i', str(exported), '-vn',
                                 '-ar', '16000', '-ac', '1', '-f', 'f32le', '-'])
    assert np.sqrt(np.mean(np.frombuffer(pcm, np.float32) ** 2)) > .001
    assert errors == []
