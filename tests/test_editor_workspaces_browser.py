"""Exercise keyless source workspace actions and their durable project state."""
import io
import os

from PIL import Image
from playwright.sync_api import sync_playwright, expect


def test_design_nodes_and_moodboard_survive_reload(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = context.new_page()
        page.set_default_timeout(20000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        base = os.environ['RAYFLOW_TEST_URL']
        try:
            page.goto(base + '/#/editor')
            page.get_by_role('button', name='Skip for now').click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)

            page.locator('[data-studio-action="workspace:design"]').click()
            expect(page.get_by_role('heading', name='AI Design Canvas')).to_be_visible()
            page.get_by_role('button', name='Title Card', exact=True).click()
            page.get_by_title('Export PNG and add it to the timeline', exact=True).click()
            page.locator('[data-studio-action="workspace:edit"]').click()
            expect(page.locator('.rayflow-editor .tl-clip')).to_have_count(1)

            page.locator('[data-studio-action="workspace:nodes"]').click()
            expect(page.get_by_role('heading', name='Node Space')).to_be_visible()
            page.get_by_placeholder('Enter prompt...', exact=True).first.fill('A jade green cinematic title')
            page.get_by_role('button', name='Add Prompt', exact=True).click()
            expect(page.get_by_placeholder('Enter prompt...', exact=True)).to_have_count(2)

            page.locator('[data-studio-action="workspace:moodboard"]').click()
            page.get_by_title('New board', exact=True).click()
            page.get_by_placeholder('Board name').fill('Judge continuity notes')
            page.get_by_placeholder('Board name').press('Enter')
            page.get_by_role('toolbar', name='Board tools').get_by_role('button', name='Note', exact=True).click()
            page.locator('.mood-stage').click(position={'x': 240, 'y': 180})
            note = page.locator('.mood-item textarea')
            note.fill('Keep the jade palette and warm key light')
            note.press('Escape')
            page.locator('.mood-item--note').dblclick()
            expect(note).to_have_value('Keep the jade palette and warm key light')
            note.press('Escape')
            page.screenshot(path=str(tmp_path / 'moodboard.png'))

            # Navigation waits for pending editor saves before unmounting.
            page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            page.locator('.rayflow-editor').wait_for(state='detached')
            session = page.request.get(base + '/api/session').json()
            project_id = session['preferences']['activeProject']
            saved = page.request.get(base + '/api/editor/projects/' + project_id).json()['project']
            assert any(element['type'] == 'text' for element in saved['designCanvas']['elements'])
            assert len(saved['timelineClips']) == 1
            assert any(node['data'].get('value') == 'A jade green cinematic title' for node in saved['nodeGraph']['nodes'])
            board = saved['storyBible']['categorizedMoodboard']
            assert any(category['label'] == 'Judge continuity notes' for category in board['categories'])
            assert any(item.get('text') == 'Keep the jade palette and warm key light' for item in board['items'])

            # The PNG must be a real private, readable asset, not a stale blob URL.
            exported = next(item for item in saved['mediaItems'] if item.get('generatedBy') == 'AI Design Canvas')
            asset_path = exported.get('url') or exported.get('path')
            if not asset_path.startswith('/api/'):
                asset_path = '/api/editor/projects/' + project_id + '/files/' + asset_path
            response = page.request.get(base + asset_path)
            assert response.ok
            png = Image.open(io.BytesIO(response.body())).convert('RGB')
            assert png.width >= 1000 and png.height >= 500
            assert len(png.getcolors(png.width * png.height)) > 10

            page.get_by_role('navigation', name='Main').get_by_role('link', name='AI Editor', exact=True).click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.reload()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:nodes"]').click()
            expect(page.get_by_placeholder('Enter prompt...', exact=True).first).to_have_value('A jade green cinematic title')
            expect(page.get_by_placeholder('Enter prompt...', exact=True)).to_have_count(2)
            page.locator('[data-studio-action="workspace:moodboard"]').click()
            page.locator('.mood-sidebar__item').filter(has_text='Judge continuity notes').click()
            expect(page.get_by_text('Keep the jade palette and warm key light', exact=True)).to_be_visible()
            assert not errors, errors
        finally:
            page.screenshot(path=str(tmp_path / 'workspace-final.png'))
            context.close()
            browser.close()


def test_project_document_import_and_scene_wall(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        context = browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = context.new_page()
        page.set_default_timeout(20000)
        base = os.environ['RAYFLOW_TEST_URL']
        script = 'INT. JADE STUDIO - DAY\nA filmmaker checks the light.\n\nEXT. RIVER BANK - NIGHT\nThe crew watches a boat pass.'
        try:
            page.goto(base + '/#/editor')
            page.get_by_role('button', name='Skip for now').click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:project"]').click()
            page.locator('[data-studio-action="project-phase:script"]').click()
            page.locator('input[type=file][accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.md,.json"]').set_input_files({
                'name': 'Judge screenplay.txt', 'mimeType': 'text/plain', 'buffer': script.encode(),
            })
            expect(page.get_by_placeholder('INT. SCENE - DAY...')).to_have_value(script)
            page.get_by_placeholder('INT. SCENE - DAY...').fill(script + '\nThe camera holds.')
            page.locator('[data-studio-action="project-phase:storyboard"]').click()
            page.get_by_role('button', name='Scene Wall', exact=True).click()
            page.get_by_role('button', name='Activate Scene Wall Pro', exact=True).click()
            expect(page.get_by_role('heading', name='Scene Wall Pro', exact=True)).to_be_visible()
            page.get_by_role('button', name='Sluglines aus Story Bible', exact=True).click()
            page.screenshot(path=str(tmp_path / 'scene-wall.png'))
            page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            page.locator('.rayflow-editor').wait_for(state='detached')
            session = page.request.get(base + '/api/session').json()
            project_id = session['preferences']['activeProject']
            saved = page.request.get(base + '/api/editor/projects/' + project_id).json()['project']
            assert saved['storyBible']['script'] == script + '\nThe camera holds.'
            assert saved['sceneWall']['enabled']
            assert 'INT. JADE STUDIO - DAY' in str(saved['sceneWall'])
            assert 'EXT. RIVER BANK - NIGHT' in str(saved['sceneWall'])
            page.goto(base + '/#/editor')
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.locator('[data-studio-action="workspace:project"]').click()
            page.locator('[data-studio-action="project-phase:script"]').click()
            expect(page.get_by_placeholder('INT. SCENE - DAY...')).to_have_value(script + '\nThe camera holds.')
        finally:
            page.screenshot(path=str(tmp_path / 'project-final.png'))
            context.close()
            browser.close()
