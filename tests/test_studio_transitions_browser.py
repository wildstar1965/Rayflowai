"""Compare real Studio preview pixels with decoded MP4 frames on the export grid."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import FFMPEG_PATH


@pytest.mark.parametrize('transition', ['crossfade', 'dip_black', 'dip_white'])
def test_mixed_rate_transition_preview_matches_export(transition, tmp_path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(base_url=os.environ['RAYFLOW_TEST_URL'], viewport={'width': 1440, 'height': 1000})
        assert context.request.post('/api/session').ok
        images = []
        for index, (color, size, rate) in enumerate([('red', '160x90', 25), ('blue', '180x320', 60)]):
            source = tmp_path / f'{index}.mp4'
            subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color={color}:s={size}:r={rate}:d=1',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)], check=True, capture_output=True)
            response = context.request.post('/api/media/images', multipart={'files': {'name': source.name, 'mimeType': 'video/mp4', 'buffer': source.read_bytes()}})
            assert response.ok, response.text()
            images += response.json()['images']
        plan = {'duration_seconds': 1.24, 'aspect_ratio': '16:9', 'fit_mode': 'fill', 'style': 'cinematic', 'color_strength': 0,
                'title': {'enabled': False}, 'clips': [
                    {'id': 'a', 'image_url': images[0]['url'], 'media_type': 'video', 'source_start': .12, 'source_duration': 1,
                     'duration': .51, 'start_time': 0, 'motion': 'static'},
                    {'id': 'b', 'image_url': images[1]['url'], 'media_type': 'video', 'source_start': .1, 'source_duration': 1,
                     'duration': .73, 'start_time': .51, 'motion': 'static'}],
                'transitions': [{'id': 'ab', 'from_clip_id': 'a', 'to_clip_id': 'b', 'type': transition, 'enabled': True, 'duration': .3}]}
        project = context.request.post('/api/editor/projects', data={'name': 'Transition verification'}).json()
        response = context.request.put(f"/api/editor/projects/{project['id']}/sequences/reel-primary", data={
            'kind': 'rayflow', 'name': 'Transitions', 'revision': 0, 'document': {'plan': plan, 'images': images, 'projectName': 'Transitions'}})
        assert response.ok, response.text()
        assert context.request.patch('/api/editor/preferences', data={'activeProject': project['id']}).ok
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('/#/studio')
        page.get_by_role('button', name='Skip for now').click()
        expect(page.locator('[data-clip-id]')).to_have_count(2)
        slider = page.get_by_role('slider', name='Playback position')
        canvas = page.locator('main canvas').first
        samples = {}
        # First, middle and last transition frames, then the incoming boundary.
        # These also exercise repeated backwards/forwards asynchronous seeking.
        for frame in [6, 10, 14, 15, 10, 6, 15]:
            slider.evaluate('''(input, value) => {
              Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, String(value));
              input.dispatchEvent(new Event('input', { bubbles: true }));
            }''', frame / 30 + .001)
            page.wait_for_timeout(200)
            samples[frame] = canvas.evaluate('c => [...c.getContext("2d").getImageData(c.width/2, c.height/2, 1, 1).data].slice(0,3)')
        canvas.screenshot(path=str(tmp_path / f'{transition}-preview.png'))
        page.get_by_role('button', name='Export MP4', exact=True).click()
        link = page.get_by_role('link', name='Download MP4', exact=True)
        expect(link).to_be_visible(timeout=120000)
        with page.expect_download() as download:
            link.click()
        output = tmp_path / f'{transition}.mp4'
        download.value.save_as(output)
        raw = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-vf', 'scale=32:18', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                             check=True, capture_output=True).stdout
        frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 18, 32, 3)
        assert len(frames) == 37
        for frame, pixel in samples.items():
            actual = frames[frame, 9, 16].astype(int)
            assert np.max(np.abs(actual - pixel)) <= 8, (transition, frame, pixel, actual.tolist())
        assert not errors, errors
        context.close()
        browser.close()
