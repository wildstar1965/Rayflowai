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
                                       env={**os.environ, 'RAYFLOW_API_PROXY_TARGET': api_url, 'AI_PROVIDER': 'local'},
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
            deadline = time.monotonic() + 60
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
        page.goto(local_servers + '/#/studio')
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
    with page.expect_response(lambda response: '/api/creative/jobs/' in response.url and response.json().get('status') == 'completed') as result:
        page.get_by_role('button', name='Generate Reel Draft').click()
    generated = result.value.json()['result']
    assert generated['aspect_ratio'] == '16:9'
    wait_plan(page, 'p.duration_seconds === 7.5')
    assert plan(page)['clips'] == generated['clips']
    expect(page.get_by_role('slider', name='Timeline playhead')).to_have_attribute('aria-valuenow', '0')
    command = page.get_by_role('textbox', name='Tell Rayflow what to edit…')
    command.fill('Make the second image last three seconds.')
    command.press('Enter')
    wait_plan(page, 'p.clips[1].duration === 3')
    edited = plan(page)
    with page.expect_request(lambda request: request.url.endswith('/api/render') and request.method == 'POST') as request:
        page.get_by_role('button', name='Export MP4', exact=True).click()
    assert request.value.post_data_json['plan'] == edited
    expect(page.get_by_role('heading', name='Your Rayflow reel is ready')).to_be_visible(timeout=120000)
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
    page.get_by_label('Find contextual B-roll on Pixabay').uncheck()
    page.get_by_label('Add clicks to spoken list items').uncheck()
    page.get_by_role('button', name='Generate Reel Draft').click()
    wait_plan(page, 'p.duration_seconds === 3')
    page.get_by_role('button', name='Captions', exact=True).click()
    expect(page.get_by_role('button', name='Generate speech captions', exact=True)).to_be_enabled(timeout=120000)
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
    expect(page.get_by_role('heading', name='Your Rayflow reel is ready')).to_be_visible(timeout=120000)
    with page.expect_download() as download:
        page.get_by_role('link', name='Download MP4').click()
    download.value.save_as(str(ROOT / 'test_artifacts/browser-video-reel.mp4'))
    assert errors == []


def test_multitrack_insert_caption_sound_controls_and_undo(studio):
    page,errors=studio
    page.evaluate(f"""() => {{
      const state=JSON.parse(localStorage.getItem('{KEY}'));
      state.plan={{...state.plan,duration_seconds:6,aspect_ratio:'16:9',title:{{...state.plan.title,enabled:false}},
        clips:[{{...state.plan.clips[0],duration:6,start_time:0,motion:'static'}}],transitions:[],
        visual_inserts:[{{id:'manual-broll',asset_id:'image',asset_url:state.images[1].url,start_time:1,duration:2,mode:'pip',position:'top_right',origin:'manual'}}],
        subtitles:[{{id:'caption',text:'A camera and a microphone',start_time:1,end_time:3,style:{{preset:'cinematic',caption_mode:'phrase',font_size:48,font_family:'Arial',color:'#FFFFFF',highlight_color:'#E7C48C',stroke_color:'#000000',stroke_width:2,position:'center_bottom'}},words:[]}}],
        sound_cues:[{{id:'cue1',label:'camera',start_time:1,sound:'soft',volume:.35,muted:false}},{{id:'cue2',label:'microphone',start_time:2.5,sound:'wood',volume:.3,muted:false}}]}};
      localStorage.setItem('{KEY}',JSON.stringify(state));
    }}""")
    page.reload()
    wait_plan(page,'p.visual_inserts?.length === 1 && p.sound_cues?.length === 2')
    insert=page.locator('footer [data-insert-id="manual-broll"]');box=insert.bounding_box();assert box
    page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down()
    page.mouse.move(box['x']+box['width']/2+37.5,box['y']+box['height']/2,steps=10);page.mouse.up()
    wait_plan(page,'Math.abs(p.visual_inserts[0].start_time-1.5)<.03')
    page.keyboard.press('Control+z');wait_plan(page,'p.visual_inserts[0].start_time===1')
    page.keyboard.press('Control+Shift+z');wait_plan(page,'Math.abs(p.visual_inserts[0].start_time-1.5)<.03')
    page.get_by_role('button',name='Inserts',exact=False).click()
    page.get_by_label('Mute click 2').check();wait_plan(page,'p.sound_cues[1].muted')
    page.get_by_label('Click 1 volume').fill('0.2');wait_plan(page,'p.sound_cues[0].volume===.2')
    page.get_by_label('Insert 1 layout').select_option('split');wait_plan(page,"p.visual_inserts[0].mode==='split'")
    page.get_by_role('button',name='Listen',exact=True).first.click()
    page.get_by_role('button',name='Captions',exact=False).click()
    editor=page.get_by_label('Caption text');editor.fill('A corrected caption');editor.press('Tab')
    wait_plan(page,"p.subtitles[0].text==='A corrected caption'")
    page.get_by_role('button',name='Inserts',exact=False).click()
    page.get_by_role('button',name='Remove',exact=True).click()
    wait_plan(page,"p.visual_inserts.length===0 && p.suppressed_auto_inserts.includes('manual-broll')")
    assert errors==[]


def test_cinematic_preset_and_manual_title_layout(studio):
    page,errors=studio
    page.get_by_role('button',name='Inserts',exact=False).click()
    page.get_by_role('button',name='Add display text',exact=True).click()
    page.get_by_label('Cinematic text',exact=True).fill('YOUR\nSTORY')
    wait_plan(page,"p.cinematic_texts[0].text==='YOUR\\nSTORY'")
    page.get_by_label('Cinematic text color',exact=True).fill('#e7c48c')
    wait_plan(page,"p.cinematic_texts[0].color==='#e7c48c'")
    page.get_by_label('Cinematic tracking',exact=True).fill('2')
    page.get_by_label('Cinematic tracking',exact=True).press('Enter')
    wait_plan(page,'p.cinematic_texts[0].tracking===2')
    page.get_by_label('Cinematic vertical position',exact=True).fill('20')
    page.get_by_label('Cinematic vertical position',exact=True).press('Enter')
    wait_plan(page,'p.cinematic_texts[0].y===.2')
    page.get_by_role('button',name='Captions',exact=False).click()
    page.get_by_role('button',name='+ Add caption',exact=True).click()
    page.get_by_role('button',name='Cinematic Warm emphasis',exact=False).click()
    wait_plan(page,"p.subtitles[0].style.preset==='cinematic' && p.subtitles[0].style.caption_mode==='phrase'")
    page.get_by_label('Caption font size',exact=True).fill('60')
    page.get_by_label('Caption font size',exact=True).press('Enter')
    wait_plan(page,'p.subtitles[0].style.font_size===60')
    page.get_by_label('Caption text',exact=True).fill('Corrected words remain editable.')
    page.get_by_label('Caption text',exact=True).press('Tab')
    wait_plan(page,"p.subtitles[0].text==='Corrected words remain editable.'")
    assert errors==[]


def test_reference_subject_preview_uses_prepared_mattes(studio):
    path=ROOT/'test_artifacts/sections67/plan.json'
    if not path.exists():path=ROOT/'test_artifacts/reference-edit-plan.json'
    if not path.exists():pytest.skip('Run verify_reference_edit.py once with the local reference reel.')
    reference_plan=json.loads(path.read_text(encoding='utf8'))
    storage = Path(os.getenv('RAYFLOW_STORAGE_DIR') or ROOT / 'backend/storage')
    if not (storage / 'uploads' / Path(reference_plan['source_filename']).name).is_file():
        pytest.skip('The opt-in reference source is not present in this test storage.')
    page,errors=studio
    page.evaluate(f"""p => {{ const state=JSON.parse(localStorage.getItem('{KEY}'));state.plan=p;
      state.images=[{{filename:p.source_filename,original_name:'Speech sample.mp4',url:p.clips[0].image_url,media_type:'video',size:1}}];
      localStorage.setItem('{KEY}',JSON.stringify(state)); }}""",reference_plan)
    with page.expect_response(lambda r:'/api/cinematic/matte' in r.url) as matte_response:
        page.reload()
    assert matte_response.value.status==200,matte_response.value.text()
    head=page.get_by_role('slider',name='Timeline playhead');head.focus();head.press('Shift+ArrowRight');head.press('Shift+ArrowRight')
    expect(head).to_have_attribute('aria-valuenow','2')
    page.wait_for_timeout(1500)
    # Compare the actual canvas against the independently encoded frame at the seek time.
    if (ROOT/'test_artifacts/sections67/9x16.mp4').exists() and path.name=='plan.json':
        import io
        import numpy as np
        import base64
        sys.path.insert(0,str(ROOT/'backend'))
        from app.core.config import FFMPEG_PATH
        data=page.locator('main canvas').evaluate("c=>({width:c.width,height:c.height,png:c.toDataURL()})")
        actual=np.asarray(Image.open(io.BytesIO(base64.b64decode(data['png'].split(',')[1]))).convert('RGB')).astype(float)
        raw=subprocess.check_output([FFMPEG_PATH,'-v','error','-ss','2','-i',str(ROOT/'test_artifacts/sections67/9x16.mp4'),'-frames:v','1','-vf',f"scale={data['width']}:{data['height']}",'-f','rawvideo','-pix_fmt','rgb24','-'])
        expected=np.frombuffer(raw,np.uint8).reshape(data['height'],data['width'],3).astype(float)
        difference=float(np.abs(actual-expected).mean())
        (ROOT/'test_artifacts/sections67/preview-comparison.json').write_text(json.dumps({'time':2,'mean_absolute_rgb_error':difference}))
        assert difference<12,difference
    else:
        assert page.locator('main canvas').evaluate("c=>c.getContext('2d').getImageData(0,0,c.width,c.height).data.some(v=>v>200)")
    page.locator('main canvas').screenshot(path=str(ROOT/'test_artifacts/reference-preview.png'))
    # Exercise moving mattes and title exit during actual playback, then seek back.
    page.get_by_role('button', name='Play', exact=True).click()
    page.wait_for_timeout(450)
    page.get_by_role('button', name='Pause', exact=True).click()
    assert float(head.get_attribute('aria-valuenow')) > 2.2
    page.get_by_title('Reset to 0s').click()
    expect(head).to_have_attribute('aria-valuenow','0')
    assert errors==[]
