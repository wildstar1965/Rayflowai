"""Real advanced editor exports, including a freshly generated in-browser asset."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import FFMPEG_PATH, FFPROBE_PATH


def test_design_to_hq_and_browser_export(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = context.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/editor')
            page.get_by_role('button', name='Skip for now').click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:design"]').click()
            page.get_by_role('button', name='Title Card', exact=True).click()
            page.get_by_title('Export PNG and add it to the timeline', exact=True).click()
            page.locator('[data-studio-action="workspace:export"]').click()
            for mode, filename in (('HQ FFmpeg', 'advanced.mp4'), ('Quick Export', 'advanced.webm')):
                page.get_by_role('button', name=mode, exact=True).click()
                page.locator('summary').filter(has_text='Resolution & Bitrate').click()
                page.get_by_label('Width', exact=True).fill('640')
                page.get_by_label('Height', exact=True).fill('360')
                page.get_by_label('FPS', exact=True).fill('24')
                if mode == 'HQ FFmpeg':
                    page.get_by_label('Hardware Encoder', exact=True).select_option('off')
                else:
                    expect(page.get_by_text('Quick Export records video only.', exact=False)).to_be_visible()
                start = page.get_by_role('button', name='Start HQ Render' if mode == 'HQ FFmpeg' else 'Start Render', exact=True)
                # Cancel a real render first, then immediately render the same
                # timeline again. Cancelled output must never become a download.
                if mode == 'HQ FFmpeg':
                    with page.expect_response(lambda response: response.url.endswith('/api/editor/jobs') and response.request.method == 'POST') as submission:
                        start.click()
                    job = submission.value.json()
                    page.get_by_role('button', name='Cancel export', exact=True).click()
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        state = context.request.get(os.environ['RAYFLOW_TEST_URL'] + '/api/editor/jobs/' + job['id']).json()
                        if state['status'] == 'cancelled': break
                        page.wait_for_timeout(100)
                    assert state['status'] == 'cancelled'
                else:
                    assets_before = context.request.get(os.environ['RAYFLOW_TEST_URL'] + '/api/editor/assets').json()
                    start.click()
                    page.wait_for_timeout(1000)
                    page.get_by_role('button', name='Cancel export', exact=True).click()
                    page.wait_for_timeout(5500)
                    assert context.request.get(os.environ['RAYFLOW_TEST_URL'] + '/api/editor/assets').json() == assets_before
                expect(page.get_by_text('Export cancelled.', exact=True)).to_be_visible()
                expect(page.get_by_role('link', name='Download Video', exact=True)).to_have_count(0)
                start.click()
                expect(page.get_by_role('heading', name='Export Complete!', exact=True)).to_be_visible(timeout=120000)
                link = page.get_by_role('link', name='Download Video', exact=True)
                assert link.get_attribute('href').startswith('/api/editor/assets/file/')
                with page.expect_download() as download:
                    link.click()
                output = tmp_path / filename
                download.value.save_as(output)
                info = json.loads(subprocess.run([FFPROBE_PATH, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)],
                                                 capture_output=True, check=True).stdout)
                stream = next(row for row in info['streams'] if row['codec_type'] == 'video')
                assert (stream['width'], stream['height']) == (640, 360)
                assert stream['codec_name'] in ('h264',) if mode == 'HQ FFmpeg' else stream['codec_name'] in ('vp8', 'vp9', 'av1')
                if info['format'].get('duration'):
                    assert abs(float(info['format']['duration']) - 5) < 0.7
                frame = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'],
                                       capture_output=True, check=True).stdout
                assert np.frombuffer(frame, dtype=np.uint8).std() > 5, 'The title card must be visible in the decoded frame.'
                page.screenshot(path=str(tmp_path / (filename + '.png')))
                if mode == 'HQ FFmpeg':
                    page.get_by_role('button', name='Export another', exact=True).click()
        finally:
            page.screenshot(path=str(tmp_path / 'export-final.png'))
            context.close()
            browser.close()
