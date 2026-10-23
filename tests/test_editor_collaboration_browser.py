"""Two authenticated browser contexts editing the same guest-owned project."""
import io
import os

from PIL import Image
from playwright.sync_api import sync_playwright, expect


def test_same_workspace_timeline_convergence_and_reload(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel='chrome')
        first = browser.new_context(viewport={'width': 1500, 'height': 1000})
        page = first.new_page()
        base = os.environ['RAYFLOW_TEST_URL']
        contexts = [first]
        dialogs = []
        try:
            page.goto(base + '/#/editor')
            page.get_by_role('button', name='Skip for now').click()
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            page.get_by_role('navigation', name='Main').get_by_role('button', name='Assets', exact=True).click()
            media = io.BytesIO()
            Image.new('RGB', (64, 64), 'green').save(media, format='PNG')
            page.get_by_role('dialog').locator('input[type=file]').set_input_files({'name': 'concurrent.png', 'mimeType': 'image/png', 'buffer': media.getvalue()})
            expect(page.get_by_role('dialog').get_by_text('concurrent.png', exact=True)).to_be_visible()
            page.get_by_role('button', name='Use in current workspace').click()
            page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            page.locator('.rayflow-editor').wait_for(state='detached')

            # Deliberately share authorization to simulate two devices in one workspace.
            second = browser.new_context(storage_state=first.storage_state(), viewport={'width': 1500, 'height': 1000})
            contexts.append(second)
            other = second.new_page()
            for tab in (page, other):
                tab.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
                tab.goto(base + '/#/editor')
                tab.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
                tab.set_default_timeout(15000)
            for tab in (page, other):
                tab.locator('.rayflow-editor [draggable=true]').filter(has=tab.get_by_text('concurrent.png', exact=True)).first.click()
            for tab in (page, other):
                expect(tab.locator('.rayflow-editor .tl-clip')).to_have_count(2, timeout=20000)
            for tab in (page, other):
                tab.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
                try:
                    tab.locator('.rayflow-editor').wait_for(state='detached')
                except Exception:
                    assert not dialogs, dialogs
                    raise
            assert not dialogs, dialogs
            page.goto(base + '/#/editor')
            page.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
            expect(page.locator('.rayflow-editor .tl-clip')).to_have_count(2)
            page.screenshot(path=str(tmp_path / 'collaboration-restored.png'))
            original_id = page.request.get(base + '/api/session').json()['preferences']['activeProject']
            for tab, script in ((page, 'First collaborator script'), (other, 'Second collaborator script')):
                tab.goto(base + '/#/editor')
                tab.locator('.rayflow-editor .app-frame').wait_for(timeout=120000)
                tab.locator('[data-studio-action="workspace:project"]').click()
                tab.locator('[data-studio-action="project-phase:script"]').click()
                tab.get_by_placeholder('INT. SCENE - DAY...').fill(script)
            page.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            page.locator('.rayflow-editor').wait_for(state='detached')
            other.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            conflict = other.get_by_role('dialog', name='Save conflict')
            expect(conflict).to_be_visible()
            conflict.get_by_role('button', name='Save as new project').click()
            expect(conflict).to_have_count(0)
            other.get_by_role('navigation', name='Main').get_by_role('link', name='Dashboard', exact=True).click()
            other.locator('.rayflow-editor').wait_for(state='detached')
            copy_id = other.request.get(base + '/api/session').json()['preferences']['activeProject']
            assert copy_id != original_id
            original = page.request.get(base + '/api/editor/projects/' + original_id).json()['project']
            copy = other.request.get(base + '/api/editor/projects/' + copy_id).json()['project']
            assert original['storyBible']['script'] == 'First collaborator script'
            assert copy['storyBible']['script'] == 'Second collaborator script'
            assert len(original['timelineClips']) == len(copy['timelineClips']) == 2
            assert not dialogs, dialogs
        finally:
            for index, context in enumerate(contexts):
                for tab in context.pages:
                    tab.screenshot(path=str(tmp_path / f'collaboration-{index}.png'))
                context.close()
            browser.close()
