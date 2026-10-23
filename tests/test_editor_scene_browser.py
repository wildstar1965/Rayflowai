"""Keyless scene blocking, 3D controls, real still capture and durable restoration."""
import io
import os

import numpy as np
from PIL import Image
from playwright.sync_api import expect, sync_playwright


def test_scene_map_and_set_design_round_trip(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(viewport={'width': 1700, 'height': 1100})
        page = context.new_page()
        page.set_default_timeout(20000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        base = os.environ['RAYFLOW_TEST_URL']
        try:
            page.goto(base + '/#/editor')
            page.get_by_role('button', name='Skip for now').click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:scene_map"]').click()
            page.locator('.palette-item').filter(has_text='Character').click()
            page.locator('.properties-panel input[type=text]').fill('Lead actor')
            page.locator('.scene-element').filter(has_text='Lead actor').hover()
            page.mouse.down()
            page.mouse.move(950, 550, steps=10)
            page.mouse.up()
            page.locator('.palette-item').filter(has_text='Camera').click()
            page.locator('.properties-panel input[type=text]').fill('Camera A')
            page.get_by_role('radio', name='3D blockout', exact=True).click()
            canvas = page.locator('.scenemap3d canvas')
            expect(canvas).to_be_visible()
            before = canvas.screenshot(path=str(tmp_path / 'map-overview.png'))
            page.get_by_role('button', name='Camera view', exact=True).click()
            page.wait_for_timeout(500)
            after = canvas.screenshot(path=str(tmp_path / 'map-camera.png'))
            assert before != after, 'Camera view must change the rendered scene.'
            page.get_by_role('button', name='Reset view', exact=True).click()
            page.get_by_role('button', name='+ New Scene', exact=True).click()
            page.get_by_role('radio', name='2D plan', exact=True).click()
            page.locator('.palette-item').filter(has_text='Light').click()
            page.locator('.properties-panel input[type=text]').fill('Warm key')

            page.locator('[data-studio-action="workspace:set_design"]').click()
            page.get_by_role('button', name='Add Box', exact=True).click()
            page.get_by_text('Primitive box', exact=True).click()
            selected = page.locator('section').filter(has=page.get_by_text('Selected Asset', exact=True))
            selected.locator('input').first.fill('Jade podium')
            selected.get_by_text('Pos x', exact=True).locator('..').locator('input').fill('2')
            selected.locator('input[type=color]').fill('#008844')
            page.get_by_role('button', name='Capture Snapshot', exact=True).click()
            expect(page.get_by_text('1920x1080 render saved to Library.', exact=True)).to_be_visible()
            page.screenshot(path=str(tmp_path / 'set-design.png'))
            page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            page.locator('.rayflow-editor').wait_for(state='detached')
            project_id = context.request.get(base + '/api/session').json()['preferences']['activeProject']
            project = context.request.get(base + '/api/editor/projects/' + project_id).json()['project']
            scenes = project['sceneMap']['scenes']
            assert len(scenes) == 2
            actor = next(item for item in scenes[0]['elements'] if item['label'] == 'Lead actor')
            assert actor['position'] != {'x': 200, 'y': 200}
            assert scenes[1]['elements'][0]['label'] == 'Warm key'
            podium = next(item for item in project['setDesign']['assets'] if item['name'] == 'Jade podium')
            assert podium['position']['x'] == 2
            snapshot = next(item for item in project['mediaItems'] if item.get('generatedBy') == 'Set Design Render')
            path = snapshot.get('url') or snapshot.get('path')
            if not path.startswith('/api/'):
                path = '/api/editor/projects/' + project_id + '/files/' + path
            response = context.request.get(base + path)
            assert response.ok
            pixels = Image.open(io.BytesIO(response.body())).convert('RGB')
            assert pixels.size == (1920, 1080)
            rgb = np.asarray(pixels).astype(int)
            assert ((rgb[:, :, 1] > rgb[:, :, 0] + 20) & (rgb[:, :, 1] > rgb[:, :, 2] + 10)).sum() > 100, 'The jade object must appear in the saved still.'
            page.goto(base + '/#/editor')
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:set_design"]').click()
            expect(page.get_by_role('button', name='Remove Jade podium', exact=True)).to_be_visible()
            page.locator('[data-studio-action="workspace:scene_map"]').click()
            page.get_by_role('button', name='Scene 1', exact=True).click()
            expect(page.locator('.scene-element').filter(has_text='Lead actor')).to_be_visible()
            expect(page.locator('.scene-element').filter(has_text='Camera A')).to_be_visible()
            assert not errors, errors
        finally:
            page.screenshot(path=str(tmp_path / 'scene-final.png'))
            context.close()
            browser.close()
