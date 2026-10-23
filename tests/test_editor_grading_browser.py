"""Grade a real shared image, round-trip a LUT, and verify HQ render colors."""
import io
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import FFMPEG_PATH


def test_color_wheels_cube_import_and_hq_output(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(viewport={'width': 1700, 'height': 1100})
        page = context.new_page()
        page.set_default_timeout(20000)
        base = os.environ['RAYFLOW_TEST_URL']
        try:
            page.goto(base + '/#/editor')
            page.get_by_role('button', name='Skip for now').click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.get_by_role('navigation', name='Main').get_by_role('button', name='Assets', exact=True).click()
            buffer = io.BytesIO()
            Image.new('RGB', (160, 90), (64, 128, 192)).save(buffer, format='PNG')
            page.get_by_role('dialog').locator('input[type=file]').set_input_files({
                'name': 'grade-source.png', 'mimeType': 'image/png', 'buffer': buffer.getvalue()})
            page.get_by_role('button', name='Use in current workspace').click()
            page.locator('.rayflow-editor [draggable=true]').filter(has=page.get_by_text('grade-source.png', exact=True)).first.click()
            page.locator('.rayflow-editor .tl-clip').click()
            page.locator('[data-studio-action="workspace:post"]').first.click()
            page.get_by_role('button', name='Warm Film', exact=True).click()
            page.get_by_role('slider', name='Gain colour', exact=True).press('ArrowRight')
            with page.expect_download() as download:
                page.get_by_role('button', name='Export .cube LUT', exact=True).click()
            cube_path = tmp_path / 'wheels.cube'
            download.value.save_as(cube_path)
            cube_text = cube_path.read_text()
            assert 'LUT_3D_SIZE 33' in cube_text
            assert len([line for line in cube_text.splitlines() if line and line[0].isdigit()]) == 33 ** 3
            page.get_by_role('button', name='Film & LUT', exact=True).click()
            rows = ['LUT_3D_SIZE 2', 'DOMAIN_MIN 0 0 0', 'DOMAIN_MAX 1 1 1']
            rows.extend(f'{1-red} {1-green} {1-blue}' for blue in range(2) for green in range(2) for red in range(2))
            page.locator('input[type=file][accept=".cube"]').set_input_files({
                'name': 'invert.cube', 'mimeType': 'text/plain', 'buffer': ('\n'.join(rows) + '\n').encode()})
            expect(page.get_by_role('option', name='Custom: invert.cube', exact=True)).to_have_count(1)
            page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            page.locator('.rayflow-editor').wait_for(state='detached')
            project_id = context.request.get(base + '/api/session').json()['preferences']['activeProject']
            document = context.request.get(base + '/api/editor/projects/' + project_id).json()['project']
            saved_lut = document['timelineClips'][0]['filters']['customLut']
            assert saved_lut['data']['__rayflowTypedArray'] == 'Float32Array'
            assert len(saved_lut['data']['values']) == 24
            page.goto(base + '/#/editor')
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:export"]').first.click()
            page.get_by_role('button', name='HQ FFmpeg', exact=True).click()
            page.locator('summary').filter(has_text='Resolution & Bitrate').click()
            page.get_by_label('Width', exact=True).fill('160')
            page.get_by_label('Height', exact=True).fill('90')
            page.get_by_label('Hardware Encoder', exact=True).select_option('off')
            page.get_by_role('button', name='Start HQ Render', exact=True).click()
            expect(page.get_by_role('heading', name='Export Complete!', exact=True)).to_be_visible(timeout=120000)
            with page.expect_download() as download:
                page.get_by_role('link', name='Download Video', exact=True).click()
            output = tmp_path / 'graded.mp4'
            download.value.save_as(output)
            frame = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-frames:v', '1', '-pix_fmt', 'rgb24',
                                    '-f', 'rawvideo', 'pipe:1'], capture_output=True, check=True).stdout
            color = np.frombuffer(frame, dtype=np.uint8).reshape(90, 160, 3)[45, 80].astype(int)
            assert np.max(np.abs(color-np.array([191, 127, 63]))) < 10, color
        finally:
            page.screenshot(path=str(tmp_path / 'grading-final.png'))
            context.close()
            browser.close()
