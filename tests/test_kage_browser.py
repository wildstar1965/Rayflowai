"""Real-browser checks for the built Kage integration (run frontend's build first)."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'test_artifacts' / 'kage'


@pytest.fixture(scope='module')
def kage_browser():
    assert (ROOT / 'frontend/dist/index.html').exists(), 'Run npm run build in frontend first'
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / 'frontend/dist'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            yield browser, f'http://127.0.0.1:{server.server_port}'
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def loaded_scene(page):
    expect(page.locator('.landing-page-frame')).to_have_attribute('data-state', 'ready')
    frame = page.locator('iframe').element_handle().content_frame()
    frame.wait_for_function('window.__kage && !document.body.classList.contains("is-locked")', timeout=60000)
    assert frame.evaluate('!!window.__kage.renderer && !window.__kage.fallback'), 'WebGL scene fell back'
    frame.wait_for_function('document.fonts.status === "loaded"')
    expect(frame.locator('#pre')).to_have_class('done')
    frame.wait_for_function('getComputedStyle(document.querySelector("#pre")).opacity === "0"')
    frame.wait_for_function('Array.from(document.querySelectorAll("#hero [data-rv], #hero .mask-line")).every(el => el.classList.contains("rv-in"))')
    return frame


def observe(page):
    errors, failed, urls = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda response: failed.append(response.url) if response.status >= 400 else None)
    page.on('requestfailed', lambda request: failed.append(request.url))
    page.on('request', lambda request: urls.append(request.url))
    return errors, failed, urls


def assert_banner_fits(page, frame):
    """The longer Rayflow banner must fit after the dolly and pointer parallax."""
    frame.wait_for_function('window.__kage.RIG.intro >= 1')
    width, height = page.viewport_size['width'], page.viewport_size['height']
    for x, y in [(1, 1), (width - 1, height - 1), (width / 2, height / 2)]:
        page.mouse.move(x, y)
        frame.wait_for_function('''() => {
            const r = window.__kage.RIG;
            return Math.abs(r.mx - r.tmx) < .002 && Math.abs(r.my - r.tmy) < .002;
        }''')
        bounds = frame.evaluate('''() => {
            const {WORD, camera} = window.__kage;
            WORD.group.updateMatrixWorld(true);
            camera.updateMatrixWorld(true);
            return [WORD.ink.xMin, WORD.ink.xMax].flatMap(x =>
                [0, WORD.ink.asc].map(y => new THREE.Vector3(x, y, 0)
                    .applyMatrix4(WORD.group.matrixWorld).project(camera)));
        }''')
        assert all(-1 <= point['x'] <= 1 for point in bounds), f'Rayflow banner clipped: {bounds}'
        if width / height >= 1.05:
            preview_top = frame.locator('.peek').bounding_box()['y']
            banner_bottom = max((1 - point['y']) * height / 2 for point in bounds)
            assert banner_bottom < preview_top, 'The preview card covers the Rayflow banner'


def test_desktop_scene_navigation_and_studio_roundtrip(kage_browser):
    browser, url = kage_browser
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = context.new_page()
    page.set_default_timeout(20000)
    errors, failed, urls = observe(page)
    try:
        page.goto(url)
        frame = loaded_scene(page)
        expect(page).to_have_title('Rayflow AI — Your story. Your rhythm.')
        expect(page.locator('iframe')).to_have_attribute('title', 'Rayflow AI — Your story. Your rhythm.')
        expect(frame.locator('.brand-tx b')).to_have_text('RAYFLOW')
        assert frame.evaluate('window.__kage.WORD.glyphs.length') == 7
        assert 'Kage' not in frame.locator('body').inner_text()
        assert 'KAGE' not in frame.locator('body').inner_text()
        for proper_name in ['Kyoto', 'Sanmon', 'Shakkei', 'Yakisugi', 'Three.js', 'Onest', 'WebGL']:
            assert proper_name in frame.locator('.page').text_content()
        assert frame.url == url + '/landing-pages/kage.html'
        assert frame.evaluate('window.innerWidth') == 1440
        assert frame.evaluate('window.innerHeight') == 900
        assert page.evaluate('document.documentElement.scrollHeight <= innerHeight')
        frame.wait_for_function('window.__kage.WORD.reveal >= 1')
        assert_banner_fits(page, frame)
        assert frame.evaluate('document.fonts.check("400 16px Onest")')
        assert 'Onest' in frame.locator('h1').evaluate('(el) => getComputedStyle(el).fontFamily')
        assert frame.locator('h1').evaluate('(el) => getComputedStyle(el).fontWeight') == '400'
        assert frame.locator('body').evaluate('(el) => getComputedStyle(el).fontWeight') == '300'
        assert frame.locator('html').evaluate('(el) => getComputedStyle(el).getPropertyValue("--vermilion").trim()') == '#e0231c'
        assert frame.locator('#threeui-page-typography').count() == 1
        frame.locator('[data-chip="0"]').hover()
        frame.wait_for_function('window.__kage.RIG.focus === 0')
        page.mouse.move(720, 400)
        frame.wait_for_function('window.__kage.RIG.focus === -1')
        page.screenshot(path=str(ARTIFACTS / 'desktop-hero.png'), animations='disabled')

        time_before = frame.evaluate('window.__kage.WORLD.uT.value')
        frame.wait_for_function('(before) => window.__kage.WORLD.uT.value > before', arg=time_before)
        frame.locator('.nav-link[href="#pathways"]').click()
        frame.wait_for_function('Math.abs(document.querySelector("#pathways").getBoundingClientRect().top) < 100')
        frame.wait_for_function('window.__kage.RIG.smooth > 1.5')
        expect(frame.locator('.nav-link[href="#pathways"]')).to_have_class('nav-link on')
        expect(frame.locator('#fg-sky [data-fg="pathways"]')).to_have_class('fg fg-active')
        frame.wait_for_function('document.querySelectorAll(".on-cloth").length === 3')
        frame.locator('.card[data-view="0"]').hover()
        page.screenshot(path=str(ARTIFACTS / 'desktop-gardens.png'), animations='disabled')

        frame.locator('#rail button[aria-label="Your workflow"]').click()
        frame.wait_for_function('Math.abs(document.querySelector("#lessons").getBoundingClientRect().top) < 100')
        frame.locator('[data-les="2"]').hover()
        frame.wait_for_function('window.__kage.RIG.focus === 2')
        frame.locator('#rail button[aria-label="Export your reel"]').click()
        frame.wait_for_function('Math.abs(document.querySelector("#eternity").getBoundingClientRect().top) < 100')
        frame.locator('.cta').click()
        frame.wait_for_function('window.scrollY < 10')
        assert not errors, errors
        assert not failed, failed
        assert all(request.startswith(url) or request.startswith('data:') for request in urls), urls

        page.get_by_role('button', name='Open Studio', exact=True).click()
        expect(page.locator('iframe')).to_have_count(0)
        expect(page.get_by_role('heading', name='Rayflow AI Director')).to_be_visible()
        assert page.locator('.rayflow-studio').evaluate('(el) => getComputedStyle(el).backgroundColor') == 'rgb(5, 7, 10)'
        assert page.locator('.rayflow-studio > header').evaluate('(el) => getComputedStyle(el).backgroundColor') == 'rgb(13, 20, 23)'
        assert page.get_by_role('button', name='Export MP4').evaluate('(el) => getComputedStyle(el).backgroundColor') == 'rgb(224, 35, 28)'
        page.screenshot(path=str(ARTIFACTS / 'rayflow-studio.png'), animations='disabled')
        page.get_by_role('button', name='Pacing', exact=True).click()
        page.get_by_role('button', name='Fast', exact=True).click()
        page.screenshot(path=str(ARTIFACTS / 'rayflow-studio-pacing.png'), animations='disabled')
        page.get_by_role('button', name='Auto Reel', exact=True).click()
        expect(page.get_by_text('Let Rayflow draft the captions, cuts, and B-roll.')).to_be_visible()
        page.screenshot(path=str(ARTIFACTS / 'rayflow-auto-reel.png'), animations='disabled')
        page.get_by_role('button', name='Cancel', exact=True).click()
        name = page.get_by_title('Click to rename project')
        name.fill('Rayflow integration check')
        name.press('Tab')
        page.get_by_title('Return to Landing Page').click()
        loaded_scene(page)
        page.get_by_role('button', name='Open Studio', exact=True).click()
        expect(page.get_by_title('Click to rename project')).to_have_value('Rayflow integration check')
        assert not errors, errors
    finally:
        context.close()


@pytest.mark.parametrize('width,height,motion', [(390, 844, 'no-preference'), (768, 1024, 'reduce')])
def test_mobile_menu_scroll_and_reduced_motion(kage_browser, width, height, motion):
    browser, url = kage_browser
    context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=True,
                                  has_touch=True, device_scale_factor=1, reduced_motion=motion)
    page = context.new_page()
    page.set_default_timeout(20000)
    errors, failed, urls = observe(page)
    try:
        page.goto(url)
        frame = loaded_scene(page)
        frame.wait_for_function('window.__kage.WORD.reveal >= 1')
        assert_banner_fits(page, frame)
        assert frame.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert frame.evaluate('window.innerWidth') == width
        page.screenshot(path=str(ARTIFACTS / f'{width}-hero.png'), animations='disabled')
        menu = frame.get_by_role('button', name='Menu', exact=True)
        menu.click()
        expect(menu).to_have_attribute('aria-expanded', 'true')
        expect(frame.locator('.nav-link[href="#pathways"]')).to_be_in_viewport()
        page.screenshot(path=str(ARTIFACTS / f'{width}-menu.png'), animations='disabled')
        page.keyboard.press('Escape')
        expect(menu).to_have_attribute('aria-expanded', 'false')
        menu.click()
        frame.locator('.nav-link[href="#pathways"]').click()
        expect(menu).to_have_attribute('aria-expanded', 'false')
        frame.wait_for_function('Math.abs(document.querySelector("#pathways").getBoundingClientRect().top) < 100')
        if motion == 'reduce':
            assert frame.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches')
            assert frame.locator('.word-mask').count() == 0
        expect(page.get_by_role('button', name='Open Studio', exact=True)).to_be_in_viewport()
        assert not errors, errors
        assert not failed, failed
        assert all(request.startswith(url) or request.startswith('data:') for request in urls), urls
    finally:
        context.close()
