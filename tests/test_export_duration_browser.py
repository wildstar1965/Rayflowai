"""Exercise actual upload, append, reorder, trim and persistence in the Studio."""
import json

import pytest
from playwright.sync_api import sync_playwright, expect

from test_studio_browser import local_servers, plan, wait_plan
from test_export_duration import sources, probe_media, probe_streams, frame_at, ARTIFACTS


def test_full_video_duration_through_studio(local_servers, sources):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(local_servers)
        page.get_by_role('button', name='Open Studio', exact=True).first.click()
        upload = page.locator('input[type=file][multiple]')
        upload.set_input_files(str(sources['ntsc']))
        wait_plan(page, 'p.clips.length === 1')
        expected_first = probe_media(sources['ntsc'])['duration']
        assert plan(page)['clips'][0]['duration'] == expected_first
        upload.set_input_files([str(sources['long']), str(sources['vfr'])])
        wait_plan(page, 'p.clips.length === 3')
        initial = plan(page)
        for clip, name in zip(initial['clips'], ['ntsc', 'long', 'vfr']):
            assert clip['duration'] == probe_media(sources[name])['duration']
            assert clip['source_duration'] == clip['duration']
            assert clip['source_start'] == 0
        assert initial['clips'][1]['duration'] > 120
        # Move the VFR clip to the front using the actual stable-ID drag handler.
        source = page.locator('[data-clip-id]').nth(2)
        target = page.locator('[data-clip-id]').first
        data = page.evaluate_handle('new DataTransfer()')
        source.dispatch_event('dragstart', {'dataTransfer': data})
        target.dispatch_event('dragover', {'dataTransfer': data, 'clientX': target.bounding_box()['x'] + 2})
        target.dispatch_event('drop', {'dataTransfer': data})
        wait_plan(page, f"p.clips[0].id === '{initial['clips'][2]['id']}'")
        reordered = plan(page)
        assert {c['id']: c['duration'] for c in reordered['clips']} == {c['id']: c['duration'] for c in initial['clips']}
        page.locator('[data-clip-id]').first.click(position={'x': 40, 'y': 25})
        page.get_by_title('Shorten clip by 0.5s').click()
        wait_plan(page, 'p.clips[0].duration === 1.9')
        assert plan(page)['clips'][0]['source_duration'] == 2.4
        page.get_by_title('Undo (Ctrl+Z)').click()
        wait_plan(page, 'p.clips[0].duration === 2.4')
        saved = plan(page)
        page.reload()
        page.get_by_role('button', name='Open Studio', exact=True).first.click()
        wait_plan(page, 'p.clips.length === 3')
        assert plan(page) == saved
        page.get_by_role('button', name='Auto Reel', exact=True).click()
        expect(page.get_by_label('Trim greetings and long quiet pauses in new drafts')).not_to_be_checked()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / 'browser-duration-plan.json').write_text(json.dumps(saved, indent=2))
        assert errors == []
        browser.close()


def test_uploaded_videos_export_download_and_play(local_servers, sources):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.goto(local_servers)
        page.get_by_role('button', name='Open Studio', exact=True).first.click()
        page.locator('input[type=file][multiple]').set_input_files([str(sources['25fps']), str(sources['vfr'])])
        wait_plan(page, 'p.clips.length === 2')
        expected = frame_at(plan(page)['duration_seconds'])
        page.get_by_role('button', name='Export MP4', exact=True).click()
        expect(page.get_by_text('Reel Export Complete', exact=True)).to_be_visible(timeout=120000)
        with page.expect_download() as download:
            page.get_by_role('link', name='Download MP4').click()
        output = ARTIFACTS / 'browser-video-export.mp4'
        download.value.save_as(str(output))
        data = probe_streams(output, count_frames=True)
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        assert int(video['nb_read_frames']) == expected
        page.get_by_role('button', name='Watch in Preview', exact=True).click()
        page.wait_for_function("() => document.querySelector('main video')?.readyState >= 2")
        element = page.locator('main video')
        assert element.evaluate('(v) => v.duration') == pytest.approx(expected / 30, abs=.022)
        element.evaluate('''async v => {
            v.muted = true;
            v.currentTime = Math.max(0, v.duration - .4);
            await v.play();
        }''')
        page.wait_for_function("() => document.querySelector('main video')?.ended", timeout=10000)
        assert element.evaluate('(v) => v.error') is None
        browser.close()
