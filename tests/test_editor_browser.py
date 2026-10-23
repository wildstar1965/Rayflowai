import io
import os
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, expect


def test_editor_guest_navigation_and_shared_asset(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(os.environ['RAYFLOW_TEST_URL'] + '/#/editor')
        page.set_default_timeout(120000)
        skip = page.get_by_role('button', name='Skip for now')
        skip.wait_for(state='visible')
        skip.click()
        page.locator('.rayflow-editor .app-frame').wait_for(state='visible', timeout=120000)
        page.screenshot(path=str(tmp_path / 'editor-desktop.png'), full_page=True)
        page.get_by_role('navigation', name='Main').get_by_role('button', name='Assets', exact=True).click()
        media = io.BytesIO()
        Image.new('RGB', (64, 64), 'green').save(media, format='PNG')
        page.get_by_role('dialog').locator('input[type=file]').set_input_files({'name': 'shared.png', 'mimeType': 'image/png', 'buffer': media.getvalue()})
        expect(page.get_by_role('dialog').get_by_text('shared.png', exact=True)).to_be_visible()
        page.get_by_role('button', name='Use in current workspace').click()
        media_card = page.locator('.rayflow-editor').locator('[draggable=true]').filter(has=page.get_by_text('shared.png', exact=True)).first
        media_card.click()
        expect(page.locator('.rayflow-editor .tl-clip')).to_have_count(1)
        expect(page.locator('.rayflow-editor').get_by_role('button', name='Undo', exact=True)).to_be_enabled()
        page.locator('.rayflow-editor').get_by_role('button', name='Undo', exact=True).click()
        expect(page.locator('.rayflow-editor .tl-clip')).to_have_count(0)
        expect(page.locator('.rayflow-editor').get_by_role('button', name='Redo', exact=True)).to_be_enabled()
        page.locator('.rayflow-editor').get_by_role('button', name='Redo', exact=True).click()
        expect(page.locator('.rayflow-editor .tl-clip')).to_have_count(1)
        page.get_by_role('navigation', name='Main').get_by_role('link', name='Studio', exact=True).click()
        page.get_by_title('Click to rename project').wait_for(state='visible', timeout=120000)
        session = page.request.get(os.environ['RAYFLOW_TEST_URL'] + '/api/session').json()
        saved = page.request.get(os.environ['RAYFLOW_TEST_URL'] + '/api/editor/projects/' + session['preferences']['activeProject']).json()
        assert len(saved['project']['timelineClips']) >= 1
        page.get_by_role('navigation', name='Main').get_by_role('button', name='Assets', exact=True).click()
        expect(page.get_by_role('dialog').get_by_text('shared.png', exact=True)).to_be_visible()
        page.get_by_role('button', name='Use in current workspace').click()
        expect(page.get_by_text('shared.png', exact=True).first).to_be_visible()
        page.get_by_role('navigation', name='Main').get_by_role('link', name='Rayflow AI', exact=True).click()
        page.locator('.rayflow-editor').wait_for(state='detached', timeout=120000)
        expect(page.get_by_role('navigation', name='Main')).to_have_count(0)
        page.get_by_role('button', name='Open Studio', exact=True).wait_for(state='visible', timeout=60000)
        frame = page.locator('iframe').element_handle().content_frame()
        expect(frame.get_by_role('link', name='AI Editor', exact=True)).to_be_visible()
        page.screenshot(path=str(tmp_path / 'landing-after-editor.png'), full_page=True)
        frame.get_by_role('link', name='AI Editor', exact=True).click()
        page.locator('.rayflow-editor .app-frame').wait_for(state='visible', timeout=120000)
        page.reload()
        page.locator('.rayflow-editor .app-frame').wait_for(state='visible', timeout=120000)
        expect(page.get_by_role('button', name='Skip for now')).to_have_count(0)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate('window.scrollTo(0, 0)')
        expect(page.get_by_label('Editor workspace', exact=True)).to_be_visible()
        panels = page.get_by_role('tablist', name='Timeline panels')
        panels.get_by_role('tab', name='Media', exact=True).click()
        expect(page.locator('.edit-browser-panel')).to_be_visible()
        panels.get_by_role('tab', name='Timeline', exact=True).click()
        expect(page.locator('.edit-center-panel')).to_be_visible()
        assert page.locator('.edit-center-panel').bounding_box()['width'] > 340
        panels.get_by_role('tab', name='Inspector', exact=True).click()
        expect(page.locator('.edit-inspector-panel')).to_be_visible()
        panels.get_by_role('tab', name='Timeline', exact=True).click()
        page.screenshot(path=str(tmp_path / 'editor-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        context.close(); browser.close()


def test_two_browser_guests_and_key_replacement(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        base = os.environ['RAYFLOW_TEST_URL']
        first, second = browser.new_context(base_url=base), browser.new_context(base_url=base)
        page, other = first.new_page(), second.new_page()
        for tab in (page, other):
            tab.goto(base + '/#/connections')
            tab.get_by_role('button', name='Skip for now').click()
            expect(tab.get_by_role('heading', name='Connections', exact=True)).to_be_visible()
        card = page.locator('.connection-grid > section').filter(has=page.get_by_role('heading', name='Google Gemini', exact=True))
        for key in ('fake-key-browser-first', 'fake-key-browser-replacement'):
            card.get_by_label('API key').fill(key)
            card.get_by_role('button', name='Save', exact=True).click()
            expect(card.get_by_text('Configured', exact=True)).to_be_visible()
            expect(card.get_by_label('API key')).to_have_value('')
            assert key not in first.request.get('/api/editor/providers').text()
            assert key not in page.evaluate('JSON.stringify(Object.entries(localStorage))')
            assert key not in page.evaluate('JSON.stringify(Object.entries(sessionStorage))')
        other_card = other.locator('.connection-grid > section').filter(has=other.get_by_role('heading', name='Google Gemini', exact=True))
        expect(other_card.get_by_text('No key saved', exact=True)).to_be_visible()
        project = first.request.post('/api/editor/projects', data={'name': 'Guest one private project'}).json()
        assert second.request.get('/api/editor/projects/' + project['id']).status == 404
        uploaded = first.request.post('/api/editor/assets', multipart={'file': {'name': 'private.txt', 'mimeType': 'text/plain', 'buffer': b'guest-one-file'}}).json()
        assert second.request.get(uploaded['url']).status == 404
        assert first.request.get(uploaded['url']).body() == b'guest-one-file'
        card.get_by_role('button', name='Remove key', exact=True).click()
        expect(card.get_by_text('No key saved', exact=True)).to_be_visible()
        page.reload()
        expect(card.get_by_text('No key saved', exact=True)).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / 'connections-mobile.png'))
        first.close(); second.close(); browser.close()
