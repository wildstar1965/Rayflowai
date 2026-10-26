"""Real Chrome decoding and pixel assertions against the canvas player.

Run against Vite using RAYFLOW_TEST_URL. No user projects or provider calls.
"""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import FFMPEG_PATH


@pytest.fixture
def preview(tmp_path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script("""window.decoders = [];
          const create = document.createElement.bind(document);
          document.createElement = function(tag, ...args) {
            const el = create(tag, ...args);
            if (tag === 'video') { window.decoders.push(el); el.seeks = 0;
              el.addEventListener('seeking', () => el.seeks++); }
            return el;
          };""")
        page.goto(os.environ['RAYFLOW_TEST_URL'] + '/tests/preview.html')
        page.wait_for_function('window.previewTest')
        yield page
        assert not errors, errors
        browser.close()


def picture(color, size=(320, 180)):
    import base64
    data = io.BytesIO()
    Image.new('RGB', size, color).save(data, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode()


def clips(transition='Cross Fade'):
    return [dict(id='a', mediaId='red', trackId='v', start=0, end=1, duration=1,
                 sourceIn=0, sourceOut=1, speed=1, transitionOut={'type': transition, 'duration': .4}),
            dict(id='b', mediaId='blue', trackId='v', start=1, end=2, duration=1,
                 sourceIn=0, sourceOut=1, speed=1)]


def set_frame(page, time, **updates):
    page.evaluate('(props) => previewTest.set(props)', {'playheadPosition': time, **updates})


def expect_pixel(page, rgb, tolerance=4):
    page.wait_for_function('([rgb, tolerance]) => previewTest.pixel().slice(0,3).every((c,i) => Math.abs(c-rgb[i]) <= tolerance)',
                           arg=[rgb, tolerance], timeout=10000)


def test_transition_endpoints_scrubbing_edits_and_lifecycle(preview):
    page = preview
    media = [dict(id='red', type='image', url=picture('red')),
             dict(id='blue', type='image', url=picture('blue', (120, 240)))]
    set_frame(page, .6, timelineClips=clips(), mediaItems=media)
    expect_pixel(page, [255, 0, 0])
    for _ in range(3):
        for time, rgb in [(.8, [128, 0, 128]), (29/30, [21, 0, 234]), (1, [0, 0, 255]), (.6, [255, 0, 0])]:
            set_frame(page, time)
            expect_pixel(page, rgb)
    # Equivalent to edit/undo/redo on the same mounted preview.
    for time in (.5, .8, 1.1):
        set_frame(page, time, isPlaying=True)
        page.wait_for_timeout(50)
        set_frame(page, time, isPlaying=False)
    original = clips()
    changed = clips()
    changed[0]['transitionOut']['duration'] = .2
    for updated, rgb in [(changed, [255, 0, 0]), (original, [128, 0, 128]), (changed, [255, 0, 0])]:
        set_frame(page, .8, timelineClips=updated)
        expect_pixel(page, rgb)
    # Gaps must not pull a future shot into an earlier transition.
    gap = clips()
    gap[1].update(start=1.5, end=2.5)
    set_frame(page, 1.2, timelineClips=gap)
    expect_pixel(page, [0, 0, 0])


def test_split_video_has_independent_decoders_and_no_stale_seek_frames(preview, tmp_path):
    page = preview
    source = tmp_path / 'split.mp4'
    result = subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=red:s=320x180:r=60:d=1',
        '-f', 'lavfi', '-i', 'color=blue:s=320x180:r=60:d=1', '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-g', '30', str(source)], capture_output=True)
    assert result.returncode == 0, result.stderr
    def serve_video(route):
        data = source.read_bytes()
        byte_range = route.request.headers.get('range')
        if byte_range:
            start, end = byte_range.removeprefix('bytes=').split('-')
            start, end = int(start or 0), int(end or len(data)-1)
            route.fulfill(status=206, body=data[start:end+1], content_type='video/mp4',
                          headers={'Accept-Ranges': 'bytes', 'Content-Range': f'bytes {start}-{end}/{len(data)}'})
        else:
            route.fulfill(body=data, content_type='video/mp4', headers={'Accept-Ranges': 'bytes'})
    page.route('**/test-media/split.mp4', serve_video)
    timeline = clips()
    timeline[1].update(mediaId='red', sourceIn=1, sourceOut=2)
    set_frame(page, .8, timelineClips=timeline, mediaItems=[dict(id='red', type='video', url='/test-media/split.mp4')])
    expect_pixel(page, [127, 0, 127], 5)
    assert page.evaluate('decoders.length') == 2
    seeks = page.evaluate('decoders.map(v => v.seeks)')
    page.wait_for_timeout(300)
    assert page.evaluate('decoders.map(v => v.seeks)') == seeks
    for _ in range(4):
        # Queue multiple seeks without waiting for decoding of obsolete times.
        for time in (1.4, .3, 1.1, .7, .8):
            set_frame(page, time)
        expect_pixel(page, [127, 0, 127], 5)
    # Hard cut must show the incoming source at the exact boundary.
    timeline[0].pop('transitionOut')
    set_frame(page, 29/30, timelineClips=timeline)
    expect_pixel(page, [253, 0, 0], 5)
    set_frame(page, 1)
    expect_pixel(page, [0, 0, 254], 5)
    for time in (.3, .8, 1.2):
        set_frame(page, time, isPlaying=True)
        page.wait_for_timeout(100)
        set_frame(page, time, isPlaying=False)
        expect_pixel(page, [253, 0, 0] if time < 1 else [0, 0, 254], 5)
    assert page.evaluate('decoders.length') == 2
    # Run the playhead continuously through a transition and cut. Every
    # presented center pixel must contain the decoded red/blue composition.
    timeline[0]['transitionOut'] = {'type': 'Cross Fade', 'duration': .4}
    set_frame(page, .3, timelineClips=timeline)
    expect_pixel(page, [253, 0, 0], 5)
    pixels = page.evaluate('''async () => {
      const pixels = [], start = performance.now();
      await new Promise(resolve => {
        const tick = now => {
          const time = .3 + (now-start)/1000;
          previewTest.set({playheadPosition: Math.min(time, 1.3), isPlaying: time < 1.3});
          pixels.push(previewTest.pixel());
          if(time < 1.3) requestAnimationFrame(tick); else resolve();
        };
        requestAnimationFrame(tick);
      });
      return pixels;
    }''')
    assert len(pixels) > 10
    assert all(pixel[0] + pixel[2] > 230 for pixel in pixels)
    page.evaluate('previewTest.unmount()')
    assert page.evaluate('decoders.every(v => v.paused && !v.getAttribute("src"))')


def test_connections_preserve_providers_account_and_teams_without_storage(preview):
    page = preview
    obsolete = []
    page.on('request', lambda request: obsolete.append(request.url) if '/editor/cloud' in request.url else None)
    page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/connections')
    page.get_by_role('button', name='Skip for now').click()
    expect(page.get_by_role('heading', name='Optional account')).to_be_visible()
    expect(page.get_by_role('heading', name='Teams and shared projects', exact=True)).to_be_visible()
    expect(page.locator('main').get_by_role('heading', name='Google Gemini', exact=True)).to_be_visible()
    text = page.locator('main').inner_text().lower()
    assert all(name not in text for name in ('cloud storage', 'dropbox', 'google drive'))
    assert not obsolete
