"""Real-browser regression checks. Requires API :8000 and Vite :5173 running."""
import json
import os
import subprocess
import sys
import time
import urllib.request
import socket
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
KEY = 'rayflow_project_state_v3'


@pytest.fixture(scope='session', autouse=True)
def local_servers():
    """Use fresh services on unused ports so user dev servers stay independent."""
    processes = []
    logs = []
    artifacts = ROOT / 'test_artifacts'
    artifacts.mkdir(exist_ok=True)
    def unused_port():
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            return sock.getsockname()[1]
    api_port, ui_port = unused_port(), unused_port()
    ui_url = f'http://127.0.0.1:{ui_port}'
    api_url = f'http://127.0.0.1:{api_port}'
    services = [
        (api_url + '/api/health', [sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', str(ROOT / 'backend'), '--host', '127.0.0.1', '--port', str(api_port)], ROOT),
        (ui_url, ['node', str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(ui_port), '--strictPort'], ROOT / 'frontend'),
    ]
    def ready(url):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.status == 200
        except Exception:
            return False
    try:
        for index, (url, command, cwd) in enumerate(services):
            if ready(url):
                continue
            log = (artifacts / f'browser-server-{index}.log').open('w', encoding='utf8')
            logs.append(log)
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=log,
                                       env={**os.environ, 'RAYFLOW_API_PROXY_TARGET': api_url},
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
            deadline = time.monotonic() + 15
            while not ready(url) and time.monotonic() < deadline and process.poll() is None:
                time.sleep(0.2)
            assert ready(url), f'Local test server did not start: {url}'
        yield ui_url
    finally:
        for process in processes:
            process.terminate()
            process.wait(timeout=5)
        for log in logs:
            log.close()


def plan(page):
    return page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}')).plan")


def wait_plan(page, expression):
    page.wait_for_function(f"() => {{ const p = JSON.parse(localStorage.getItem('{KEY}'))?.plan; return p && ({expression}); }}")


@pytest.fixture
def studio(tmp_path, local_servers):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(15000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(local_servers)
        page.get_by_role('button', name='Open Studio', exact=True).first.click()
        paths = []
        for i, color in enumerate(['red', 'green', 'blue']):
            path = tmp_path / f'browser_{i}.png'
            image = Image.new('RGB', (640, 360), color)
            ImageDraw.Draw(image).rectangle((50, 50, 590, 310), outline='white', width=4)
            image.save(path)
            paths.append(str(path))
        page.locator('input[type=file][multiple]').set_input_files(paths)
        wait_plan(page, 'p.clips.length === 3')
        yield page, errors
        context.close()
        browser.close()


def test_layout_playhead_trimming_undo_reorder_and_playback(studio):
    page, errors = studio
    head = page.get_by_role('slider', name='Timeline playhead')
    for width, height in [(1440, 900), (1280, 720), (1024, 600), (768, 600), (390, 650)]:
        page.set_viewport_size({'width': width, 'height': height})
        for ratio in ['16:9', '9:16', '1:1']:
            page.get_by_role('button', name=ratio, exact=True).click()
            controls = page.get_by_test_id('playback-controls').bounding_box()
            canvas = page.locator('main canvas').bounding_box()
            assert controls and canvas and canvas['height'] > 30
            assert controls['y'] + controls['height'] <= height
            assert canvas['y'] + canvas['height'] <= controls['y'] + 1
            expected = {'16:9': 16 / 9, '9:16': 9 / 16, '1:1': 1}[ratio]
            assert abs(canvas['width'] / canvas['height'] - expected) < 0.03
            assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1')
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.get_by_role('button', name='16:9', exact=True).click()

    def drag_head(target, scale=75):
        box = head.bounding_box()
        before = float(head.get_attribute('aria-valuenow'))
        x = box['x'] + box['width'] / 2 + 3
        y = box['y'] + 8
        page.mouse.move(x, y)
        page.mouse.down()
        assert float(head.get_attribute('aria-valuenow')) == pytest.approx(before, abs=0.02)
        page.mouse.move(x + (target - before) * scale, y + 30, steps=12)
        page.mouse.up()
        expect(head).to_have_attribute('aria-valuenow', str(target))

    drag_head(3)
    first = page.locator('main canvas').screenshot()
    drag_head(7)
    assert page.locator('main canvas').screenshot() != first
    page.get_by_title('Zoom In Timeline', exact=True).click()
    page.get_by_title('Zoom In Timeline', exact=True).click()
    head.evaluate('(el) => el.parentElement.parentElement.scrollLeft = 500')
    drag_head(10, 112.5)
    head.focus()
    head.press('End')
    assert float(head.get_attribute('aria-valuenow')) == 15
    head.press('Home')
    head.evaluate('(el) => el.parentElement.parentElement.scrollLeft = 0')

    initial = plan(page)
    clip = page.locator('[data-clip-id]').first
    clip.click(position={'x': 40, 'y': 25})
    trim = clip.get_by_title('Drag right edge to trim duration').bounding_box()
    page.mouse.move(trim['x'] + 4, trim['y'] + 10)
    page.mouse.down()
    page.mouse.move(trim['x'] + 4 - 112.5, trim['y'] + 10, steps=10)
    page.mouse.up()
    wait_plan(page, 'p.clips[0].duration === 4')
    page.get_by_title('Undo (Ctrl+Z)').click()
    wait_plan(page, 'p.clips[0].duration === 5')
    page.get_by_title('Redo', exact=True).click()
    wait_plan(page, 'p.clips[0].duration === 4')
    page.get_by_title('Undo (Ctrl+Z)').click()

    # Native drag events exercise the existing stable-ID reorder handler.
    source = page.locator('[data-clip-id]').nth(2)
    target = page.locator('[data-clip-id]').nth(0)
    data = page.evaluate_handle('new DataTransfer()')
    source.dispatch_event('dragstart', {'dataTransfer': data})
    target.dispatch_event('dragover', {'dataTransfer': data, 'clientX': target.bounding_box()['x'] + 2})
    target.dispatch_event('drop', {'dataTransfer': data})
    wait_plan(page, f"p.clips[0].id === '{initial['clips'][2]['id']}'")
    page.get_by_title('Undo (Ctrl+Z)').click()
    wait_plan(page, f"p.clips[0].id === '{initial['clips'][0]['id']}'")
    for _ in range(3):
        page.get_by_role('button', name='Play', exact=True).click()
        page.wait_for_timeout(250)
        page.get_by_role('button', name='Pause', exact=True).click()
    assert float(head.get_attribute('aria-valuenow')) > 0.4
    page.get_by_title('Reset to 0s').click()
    expect(head).to_have_attribute('aria-valuenow', '0')
    artifacts = ROOT / 'test_artifacts'
    artifacts.mkdir(exist_ok=True)
    page.screenshot(path=str(artifacts / 'studio-landscape.png'))
    saved_plan = plan(page)
    page.reload()
    page.get_by_role('button', name='Open Studio', exact=True).first.click()
    wait_plan(page, 'p.clips.length === 3')
    assert plan(page) == saved_plan
    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_title('New / Clear Project', exact=True).click()
    wait_plan(page, 'p.clips.length === 0')
    expect(page.get_by_title('Undo (Ctrl+Z)')).to_be_disabled()
    assert errors == []


def test_auto_reel_command_preview_export(studio):
    page, errors = studio
    page.get_by_role('button', name='16:9', exact=True).click()
    page.get_by_role('button', name='Auto Reel', exact=True).click()
    page.get_by_label('Generate captions from speech').uncheck()
    with page.expect_response(lambda response: '/api/auto-edit' in response.url) as result:
        page.get_by_role('button', name='Generate Reel Draft').click()
    generated = result.value.json()
    assert generated['aspect_ratio'] == '16:9'
    wait_plan(page, 'p.duration_seconds === 7.5')
    assert plan(page)['clips'] == generated['clips']
    expect(page.get_by_role('slider', name='Timeline playhead')).to_have_attribute('aria-valuenow', '0')
    command = page.get_by_placeholder('Type or speak your direction...')
    command.fill('Make the second image last three seconds.')
    command.press('Enter')
    wait_plan(page, 'p.clips[1].duration === 3')
    edited = plan(page)
    with page.expect_request(lambda request: request.url.endswith('/api/render') and request.method == 'POST') as request:
        page.get_by_role('button', name='Export MP4', exact=True).click()
    assert request.value.post_data_json['plan'] == edited
    expect(page.get_by_text('Reel Export Complete', exact=True)).to_be_visible(timeout=120000)
    with page.expect_download() as download:
        page.get_by_role('link', name='Download MP4').click()
    artifacts = ROOT / 'test_artifacts'
    artifacts.mkdir(exist_ok=True)
    download.value.save_as(str(artifacts / 'browser-auto-reel.mp4'))
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.core.config import FFMPEG_PATH
    frames = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(artifacts / 'browser-auto-reel.mp4'),
        '-vf', 'scale=2:2', '-pix_fmt', 'gray', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'],
        capture_output=True, check=True).stdout
    assert len(frames) // 4 == round(edited['duration_seconds'] * 30)
    page.get_by_role('button', name='Watch in Preview', exact=True).click()
    page.locator('main video').evaluate('(video) => video.pause()')
    assert page.locator('main video').get_attribute('src').endswith('/download')
    (artifacts / 'browser-plan.json').write_text(json.dumps(edited, indent=2), encoding='utf8')
    assert errors == []


def test_video_only_auto_reel_and_seeking(studio, tmp_path):
    import subprocess
    import sys
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.core.config import FFMPEG_PATH
    page, errors = studio
    page.get_by_role('button', name='Clear All', exact=True).click()
    video = tmp_path / 'talking-head-fixture.mp4'
    subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=size=640x360:rate=30:duration=3', '-f', 'lavfi', '-i',
        'sine=frequency=700:duration=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', str(video)], check=True)
    page.locator('input[type=file][multiple]').set_input_files(str(video))
    wait_plan(page, "p.clips.length === 1 && p.clips[0].media_type === 'video'")
    page.get_by_role('button', name='Auto Reel', exact=True).click()
    page.get_by_label('Generate captions from speech').uncheck()
    page.get_by_role('button', name='Generate Reel Draft').click()
    wait_plan(page, 'p.duration_seconds === 3')
    page.get_by_role('button', name='Captions', exact=True).click()
    expect(page.get_by_role('button', name='Transcribe', exact=False)).to_be_enabled()
    head = page.get_by_role('slider', name='Timeline playhead')
    page.wait_for_function("() => {const c=document.querySelector('main canvas'); return c && c.getContext('2d').getImageData(100,100,1,1).data[0] !== 39;}")
    initial = page.locator('main canvas').screenshot()
    head.focus()
    head.press('Shift+ArrowRight')
    expect(head).to_have_attribute('aria-valuenow', '1')
    page.wait_for_timeout(300)  # Allow the HTMLVideoElement to decode the seeked frame.
    assert page.locator('main canvas').screenshot() != initial
    page.get_by_role('button', name='Play', exact=True).click()
    page.wait_for_timeout(400)
    page.get_by_role('button', name='Pause', exact=True).click()
    assert float(head.get_attribute('aria-valuenow')) > 1.2
    page.get_by_role('button', name='Export MP4', exact=True).click()
    expect(page.get_by_text('Reel Export Complete', exact=True)).to_be_visible(timeout=120000)
    with page.expect_download() as download:
        page.get_by_role('link', name='Download MP4').click()
    download.value.save_as(str(ROOT / 'test_artifacts/browser-video-reel.mp4'))
    assert errors == []
