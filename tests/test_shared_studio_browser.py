"""Real Studio upload, Auto Reel, caption import, preview and FFmpeg download."""
import io
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.media import probe_media


def test_shared_studio_reel_captions_and_real_render(tmp_path):
    picture = io.BytesIO(); Image.new('RGB', (640, 360), (32, 155, 70)).save(picture, format='PNG')
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes((np.sin(2 * np.pi * 440 * np.arange(72000) / 24000) * 4000).astype('<i2').tobytes())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(base_url=os.environ['RAYFLOW_TEST_URL'], viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = context.new_page(); errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_default_timeout(30000)
        page.goto('/#/studio')
        page.get_by_role('button', name='Skip for now').click()
        page.locator('input[type=file][multiple]').set_input_files({'name': 'judging-frame.png', 'mimeType': 'image/png', 'buffer': picture.getvalue()})
        expect(page.get_by_text('judging-frame.png', exact=True).first).to_be_visible()
        page.get_by_role('button', name='16:9', exact=True).click()
        page.get_by_role('button', name='Auto Reel', exact=True).click()
        page.get_by_label('Generate captions from speech', exact=True).uncheck()
        page.get_by_label('Find contextual B-roll on Pixabay', exact=True).uncheck()
        page.get_by_label('Add clicks to spoken list items', exact=True).uncheck()
        page.get_by_role('button', name='Generate Reel Draft', exact=True).click()
        expect(page.get_by_role('button', name='Close Auto Reel')).to_have_count(0, timeout=120000)
        page.get_by_role('button', name='Music', exact=True).click()
        page.locator('input[type=file][accept="audio/*"]').set_input_files({'name': 'judging-tone.wav', 'mimeType': 'audio/wav', 'buffer': audio.getvalue()})
        expect(page.get_by_text('judging-tone.wav', exact=True).first).to_be_visible(timeout=120000)
        page.get_by_role('button', name='Captions', exact=True).click()
        subtitles = [{'id': 'judge-caption', 'text': 'Rayflow shared project', 'start_time': 0.1, 'end_time': 2.0}]
        page.get_by_label('Import caption JSON', exact=True).set_input_files({'name': 'captions.json', 'mimeType': 'application/json',
            'buffer': json.dumps({'format': 'rayflow-captions-v1', 'subtitles': subtitles}).encode()})
        expect(page.get_by_text('Captions imported. Undo restores the previous captions.')).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role('button', name='Download captions', exact=True).click()
        caption_path = tmp_path / 'captions.srt'; download.value.save_as(caption_path)
        assert 'Rayflow shared project' in caption_path.read_text(encoding='utf8')
        page.locator('main canvas').screenshot(path=str(tmp_path / 'studio-caption-preview.png'))
        page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
        session = context.request.get('/api/session').json()
        project_id = session['preferences']['activeProject']
        project = context.request.get('/api/editor/projects/' + project_id).json()
        reel = next(sequence for sequence in project['sequences'] if sequence['kind'] == 'rayflow')
        assert reel['document']['plan']['clips'] and reel['document']['plan']['subtitles'][0]['text'] == 'Rayflow shared project'
        page.get_by_role('navigation', name='Main').get_by_role('link', name='Studio', exact=True).click()
        page.get_by_role('button', name='Export MP4', exact=True).click()
        link = page.get_by_role('link', name='Download MP4', exact=True)
        expect(link).to_be_visible(timeout=180000)
        with page.expect_download() as download:
            link.click()
        output = tmp_path / 'studio-render.mp4'; download.value.save_as(output)
        info = probe_media(output)
        assert info['has_video'] and info['has_audio']
        assert info['width'] > info['height']
        assert abs(info['duration'] - reel['document']['plan']['duration_seconds']) < .2
        assert not errors, errors
        context.close(); browser.close()
