"""Regressions for editor ancestor scrolling, route initialization and retry."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import FFMPEG_PATH


def open_editor(page):
    page.set_default_timeout(30000)
    page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/editor')
    page.get_by_role('button', name='Skip for now').click()
    page.locator('.app-frame:not([inert])').wait_for(timeout=120000)
    expect(page.locator('.rayflow-loading')).to_have_count(0)


def test_editor_layout_and_compact_setup(tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width':1440, 'height':1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/editor')
        dialog = page.get_by_role('dialog', name='Welcome to Rayflow AI')
        expect(dialog).to_be_visible(timeout=120000)
        assert dialog.bounding_box()['width'] <= 768
        assert dialog.bounding_box()['height'] <= 800
        expect(dialog.get_by_role('button', name='Skip for now')).to_be_in_viewport()
        expect(dialog.get_by_label('API key').first).to_be_visible()
        page.screenshot(path=str(tmp_path / 'setup-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        expect(dialog.get_by_role('button', name='Skip for now')).to_be_in_viewport()
        assert dialog.bounding_box()['width'] <= 390
        page.screenshot(path=str(tmp_path / 'setup-mobile.png'))
        dialog.get_by_role('button', name='Skip for now').click()
        page.locator('.app-frame:not([inert])').wait_for(timeout=120000)
        measurements = {}
        for width, height in [(1440,1000),(1366,768),(1024,768),(390,844),(844,390),(1920,1080)]:
            page.set_viewport_size({'width':width,'height':height})
            page.wait_for_function('document.fonts.status === "loaded"')
            # This reproduced a 265px ancestor scroll in the original code.
            result = page.evaluate('''() => {
                const rect = s => { const r=document.querySelector(s).getBoundingClientRect(); return {top:r.top,bottom:r.bottom,width:r.width,height:r.height}; };
                return {nav:rect('.workspace-nav'),editor:rect('.rayflow-editor'),frame:rect('.app-frame'),body:rect('.app-frame__body'),workspace:rect('.edit-workspace'),center:rect('.edit-center-panel'),preview:rect('.edit-monitor-panel'),timeline:rect('.edit-timeline-surface'),scroll:document.querySelector('.app-frame').scrollTop,documentWidth:document.documentElement.scrollWidth};
            }''')
            measurements[f'{width}x{height}'] = result
            assert abs(result['editor']['bottom'] - height) <= 1, result
            assert abs(result['editor']['top'] - result['nav']['bottom']) <= 1, result
            assert result['body']['top'] >= result['nav']['bottom'], result
            assert result['scroll'] == 0, result
            assert result['preview']['height'] >= 270, result
            assert result['timeline']['height'] >= 178, result
            assert result['documentWidth'] <= width, result
            if height >= 768:
                assert abs(result['timeline']['bottom'] - result['center']['bottom']) <= 2, result
            else:
                page.locator('.edit-center-panel').evaluate('(e) => e.scrollTop = e.scrollHeight')
                expect(page.locator('.tl-header')).to_be_in_viewport()
            if width <= 1280:
                tabs = page.get_by_role('tablist', name='Timeline panels')
                tabs.get_by_role('tab', name='Media', exact=True).click()
                expect(page.locator('.edit-browser-panel')).to_be_visible()
                tabs.get_by_role('tab', name='Inspector', exact=True).click()
                expect(page.locator('.edit-inspector-panel')).to_be_visible()
                tabs.get_by_role('tab', name='Timeline', exact=True).click()
                expect(page.locator('.rayflow-loading')).to_have_count(0)
            if width < 900:
                pages = page.get_by_role('navigation', name='Post pages')
                pages.get_by_role('tab', name='Deliver', exact=True).scroll_into_view_if_needed()
                expect(pages.get_by_role('tab', name='Deliver', exact=True)).to_be_in_viewport()
                pages.get_by_role('tab', name='Media', exact=True).scroll_into_view_if_needed()
                expect(pages.get_by_role('tab', name='Media', exact=True)).to_be_in_viewport()
            page.screenshot(path=str(tmp_path / f'editor-{width}x{height}.png'))
        (tmp_path / 'measurements.json').write_text(json.dumps(measurements, indent=2))
        # The resize handle must move in the pointer's direction without
        # accumulating the full drag distance on every mouse event.
        divider = page.locator('.edit-divider-h')
        before = divider.bounding_box()
        page.mouse.move(before['x'] + before['width']/2, before['y'] + before['height']/2)
        page.mouse.down()
        page.mouse.move(before['x'] + before['width']/2, before['y'] + before['height']/2 + 40, steps=8)
        page.mouse.up()
        after = divider.bounding_box()
        assert 20 < after['y'] - before['y'] < 60
        divider.dblclick()
        assert not errors, errors
        browser.close()


def test_initial_project_loading_and_retry(tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width':1366,'height':768})
        held = []
        def hold_project(route):
            if route.request.method == 'GET' and '/files/' not in route.request.url:
                held.append(route)
            else:
                route.continue_()
        page.route('**/api/editor/projects/*', hold_project)
        page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/editor')
        page.get_by_role('button', name='Skip for now').click(timeout=120000)
        expect(page.get_by_role('status').filter(has_text='Restoring your project')).to_be_visible(timeout=120000)
        page.wait_for_function('document.querySelector(".rayflow-editor") !== null')
        # Let pending network routing callbacks run before checking the gate.
        expect(page.locator('.rayflow-editor .rayflow-loading')).to_be_visible()
        assert held
        page.screenshot(path=str(tmp_path / 'loading.png'))
        held[0].fulfill(status=503, content_type='application/json', body=json.dumps({'detail':'Project storage temporarily unavailable'}))
        expect(page.get_by_role('alert')).to_contain_text('Project storage temporarily unavailable')
        page.screenshot(path=str(tmp_path / 'loading-error.png'))
        page.unroute('**/api/editor/projects/*', hold_project)
        page.get_by_role('button', name='Retry', exact=True).click()
        page.locator('.app-frame:not([inert])').wait_for(timeout=120000)
        expect(page.locator('.rayflow-loading')).to_have_count(0)
        expect(page.locator('.tl-track')).to_have_count(2)
        browser.close()


def test_preview_media_error_retry_preserves_restored_timeline(tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width':1440,'height':1000})
        fixture_url = '/api/editor/assets/file/opening-preview.png'
        def project_fixture(route):
            if route.request.method != 'GET' or '/files/' in route.request.url:
                route.continue_(); return
            response = route.fetch()
            data = response.json()
            if 'project' in data:
                data['project']['mediaItems'] = [{'id':'fixture','type':'image','name':'Opening preview','path':fixture_url}]
                data['project']['timelineClips'] = [{'id':'clip','mediaId':'fixture','trackId':'video-1','start':0,'end':5,'sourceIn':0,'sourceOut':5,'duration':5}]
            route.fulfill(response=response, json=data)
        page.route('**/api/editor/projects/*', project_fixture)
        page.route('**' + fixture_url, lambda route: route.fulfill(status=404))
        page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/editor')
        page.get_by_role('button', name='Skip for now').click(timeout=120000)
        expect(page.get_by_role('alert')).to_contain_text('opening preview', timeout=120000)
        expect(page.locator('.app-frame')).to_have_attribute('inert','')
        media = io.BytesIO()
        Image.new('RGB',(64,64),'green').save(media,format='PNG')
        page.unroute('**' + fixture_url)
        page.route('**' + fixture_url, lambda route: route.fulfill(status=200, content_type='image/png', body=media.getvalue()))
        page.get_by_role('button', name='Retry', exact=True).click()
        page.locator('.app-frame:not([inert])').wait_for(timeout=120000)
        expect(page.locator('.tl-clip')).to_have_count(1)
        expect(page.locator('.rayflow-loading')).to_have_count(0)
        page.screenshot(path=str(tmp_path / 'preview-retry.png'))
        browser.close()


def test_video_audio_playback_and_restore(tmp_path):
    video = tmp_path / 'preview-video.mp4'
    audio = tmp_path / 'preview-audio.wav'
    subprocess.run([FFMPEG_PATH, '-v','error','-f','lavfi','-i','color=c=green:s=320x180:r=24','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(video)], check=True)
    subprocess.run([FFMPEG_PATH, '-v','error','-f','lavfi','-i','sine=frequency=440:duration=2',str(audio)], check=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width':1600,'height':1000})
        open_editor(page)
        for asset in (video, audio):
            page.get_by_role('navigation', name='Main').get_by_role('button', name='Assets', exact=True).click()
            page.get_by_role('dialog').locator('input[type=file]').set_input_files(str(asset))
            asset_row = page.get_by_role('dialog').get_by_role('listitem').filter(has=page.get_by_text(asset.name, exact=True))
            asset_row.get_by_role('button', name='Use in current workspace').click()
            card = page.locator('.rayflow-editor [draggable=true]').filter(has=page.get_by_text(asset.name, exact=True)).first
            if asset == video:
                card.drag_to(page.locator('.tl-track__lane').first, target_position={'x':8,'y':28})
            else:
                card.click()
        expect(page.locator('.tl-clip')).to_have_count(2)
        expect(page.locator('.tl-clip--audio')).to_have_count(1)
        page.get_by_title('Play (Space)', exact=True).click()
        page.wait_for_function('Number(document.querySelector(".edit-transport input[type=range]").value) > .75')
        green_frame = '''() => { const c=document.querySelector('.edit-monitor-panel canvas'); const pixel=c.getContext('2d').getImageData(c.width/2,c.height/2,1,1).data; return pixel[1] > 80 && pixel[1] > pixel[0] + pixel[2]; }'''
        page.wait_for_function(green_frame)
        page.get_by_title('Pause (Space)', exact=True).click()
        assert page.locator('.app-frame').evaluate('(e) => e.scrollTop') == 0
        page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
        page.locator('.rayflow-editor').wait_for(state='detached')
        page.get_by_role('navigation', name='Main').get_by_role('link', name='AI Editor', exact=True).click()
        page.locator('.app-frame:not([inert])').wait_for(timeout=120000)
        expect(page.locator('.tl-clip')).to_have_count(2)
        expect(page.locator('.tl-clip--audio')).to_have_count(1)
        expect(page.locator('.rayflow-loading')).to_have_count(0)
        page.get_by_title('Play (Space)', exact=True).click()
        page.wait_for_function(green_frame)
        page.get_by_title('Pause (Space)', exact=True).click()
        page.screenshot(path=str(tmp_path / 'video-audio-restored.png'), animations='disabled')
        browser.close()
