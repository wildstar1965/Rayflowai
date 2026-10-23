"""Browser coverage against a running Vite development or preview server."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect

URL = os.getenv('RAYFLOW_TEST_URL', 'http://127.0.0.1:5181')


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.set_default_timeout(20000)
        yield page
        browser.close()


def test_initialization_failure_retry_and_scene_loading(page):
    page.route('**/api/health', lambda route: route.fulfill(status=503, json={'detail': 'offline'}))
    page.goto(URL)
    expect(page.get_by_text('The video engine is unavailable')).to_be_visible()
    expect(page.get_by_role('button', name='Open Studio')).to_have_count(0)
    expect(page.locator('iframe')).to_have_count(0)
    page.unroute('**/api/health')
    page.route('**/api/health', lambda route: route.fulfill(json={'status': 'healthy'}))
    page.route('**/landing-pages/kage.html', lambda route: route.fulfill(content_type='text/html', body='<body class="is-locked"><div id="pre">Loading preview</div></body>'))
    page.get_by_role('button', name='Retry connection').click()
    expect(page.locator('iframe')).to_be_visible()
    expect(page.get_by_role('button', name='Open Studio')).to_have_count(0)
    frame = page.locator('iframe').element_handle().content_frame()
    frame.evaluate("document.querySelector('#pre').classList.add('done'); document.body.classList.remove('is-locked')")
    expect(page.get_by_role('button', name='Open Studio')).to_be_visible()


def test_settings_have_no_returned_credentials_and_connection_errors(page):
    page.route('**/api/health', lambda route: route.fulfill(json={'status': 'healthy'}))
    page.route('**/api/settings', lambda route: route.fulfill(json={'openrouter_configured': True, 'openrouter_model': 'test/model', 'pixabay_configured': False, 'ollama_host': 'http://127.0.0.1:11434', 'ollama_model': 'qwen3:8b', 'ai_provider': 'auto', 'editable': True}))
    page.route('**/api/ollama/status', lambda route: route.fulfill(json={'available': False, 'host': 'http://127.0.0.1:11434', 'models': [], 'error': 'Ollama is offline'}))
    page.goto(URL + '/#/connections')
    expect(page.get_by_role('heading', name='Connections')).to_be_visible()
    expect(page.get_by_role('alert')).to_have_text('Ollama is offline')
    assert page.locator('input[type=password]').count() == 2
    assert all(value == '' for value in page.locator('input[type=password]').evaluate_all('(inputs) => inputs.map(input => input.value)'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    artifacts = Path(__file__).resolve().parents[1] / 'test_artifacts'
    artifacts.mkdir(exist_ok=True)
    page.screenshot(path=str(artifacts / 'phase8-connections-mobile.png'), full_page=True)


@pytest.mark.parametrize('width', [390, 768, 1440])
def test_real_landing_links_and_caption_entry(page, width):
    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/api/health', lambda route: route.fulfill(json={'status': 'healthy'}))
    page.goto(URL)
    expect(page.get_by_role('button', name='Open Studio')).to_be_visible(timeout=45000)
    frame = page.locator('iframe').element_handle().content_frame()
    expect(frame.locator('#cards [role=link]')).to_have_count(3)
    assert frame.locator('.nav-links .nav-link').evaluate_all('(links) => links.every(link => link.href.includes("/#/"))')
    assert frame.locator('.foot-grid li a').evaluate_all('(links) => links.every(link => link.href.includes("/#/"))')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    card = frame.get_by_role('link', name='Smart Captions', exact=True).first
    card.focus()
    card.press('Enter')
    expect(page).to_have_url(URL + '/#/studio/captions')
    expect(page.get_by_role('button', name='Smart phrases')).to_be_visible()
    expect(page.get_by_role('button', name='Export timeline', exact=True)).to_be_visible()


def test_dashboard_empty_state_and_recorded_metrics(page):
    page.route('**/api/health', lambda route: route.fulfill(json={'status': 'healthy'}))
    data = {'total_jobs': 0, 'active_jobs': 0, 'completed_jobs': 0, 'failed_jobs': 0, 'cancelled_jobs': 0, 'interrupted_jobs': 0, 'exports': 0, 'caption_jobs': 0, 'average_render_seconds': None, 'success_rate': None, 'recent_jobs': [], 'daily_activity': []}
    page.route('**/api/analytics', lambda route: route.fulfill(json=data))
    page.goto(URL + '/#/dashboard')
    expect(page.get_by_text('No processing jobs yet.', exact=False)).to_be_visible()
    expect(page.locator('.metric-card').filter(has=page.get_by_role('heading', name='Processing success')).locator('strong')).to_have_text('—')
    data.update(total_jobs=3, exports=2, completed_jobs=2, failed_jobs=1, success_rate=200/3, average_render_seconds=12)
    page.get_by_role('button', name='Refresh activity').click()
    expect(page.locator('.metric-card').filter(has=page.get_by_role('heading', name='Completed exports')).locator('strong')).to_have_text('2')
    expect(page.locator('.metric-card').filter(has=page.get_by_role('heading', name='Processing success')).locator('strong')).to_have_text('66.7%')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(Path(__file__).resolve().parents[1] / 'test_artifacts' / 'phase8-dashboard-mobile.png'), full_page=True)


def test_dashboard_handles_corrupt_project_and_failed_refresh(page):
    page.route('**/api/health', lambda route: route.fulfill(json={'status': 'healthy'}))
    data = {'total_jobs': 2, 'active_jobs': 0, 'completed_jobs': 2, 'failed_jobs': 0, 'cancelled_jobs': 0, 'interrupted_jobs': 0,
            'exports': 2, 'caption_jobs': 0, 'average_render_seconds': 3, 'success_rate': 100, 'recent_jobs': [],
            'daily_activity': [{'date': '2026-10-23', 'completed': 2, 'failed': 0, 'exports': 2}]}
    page.route('**/api/analytics', lambda route: route.fulfill(json=data))
    page.add_init_script("localStorage.setItem('rayflow_project_state_v3', JSON.stringify({projectName:{invalid:true}}))")
    page.goto(URL + '/#/dashboard')
    expect(page.get_by_text('The saved project could not be read on this device.')).to_be_visible()
    expect(page.get_by_role('cell', name='2026-10-23')).to_be_visible()
    page.unroute('**/api/analytics')
    page.route('**/api/analytics', lambda route: route.fulfill(status=503, json={'detail': 'History temporarily unavailable'}))
    page.get_by_role('button', name='Refresh activity').click()
    expect(page.get_by_role('alert')).to_contain_text('Previously loaded values are shown.')
    expect(page.locator('.metric-card').filter(has=page.get_by_role('heading', name='Completed exports')).locator('strong')).to_have_text('2')


def test_ollama_model_selection_save_and_prompt_display(page):
    page.route('**/api/health', lambda route: route.fulfill(json={'status': 'healthy'}))
    settings = {'openrouter_configured': False, 'openrouter_model': 'test/model', 'pixabay_configured': False,
                'ollama_host': 'http://127.0.0.1:11434', 'ollama_model': 'one:latest', 'ai_provider': 'ollama', 'editable': True}
    def configuration(route):
        if route.request.method == 'PUT':
            settings['ollama_model'] = route.request.post_data_json['values']['OLLAMA_MODEL']
        route.fulfill(json=settings)
    page.route('**/api/settings', configuration)
    page.route('**/api/ollama/status', lambda route: route.fulfill(json={'available': True, 'ready': True,
        'host': settings['ollama_host'], 'models': ['one:latest', 'two:latest'], 'default_model': settings['ollama_model']}))
    def prompt(route):
        assert route.request.post_data_json['model'] == 'two:latest'
        route.fulfill(json={'response': 'Test model response'})
    page.route('**/api/ollama/test', prompt)
    page.goto(URL + '/#/connections')
    expect(page.get_by_text('Connected. 2 installed model(s).')).to_be_visible()
    page.get_by_label('Installed model').select_option('two:latest')
    page.get_by_role('button', name='Save configuration').click()
    expect(page.get_by_text('Connected. 2 installed model(s).')).to_be_visible()
    assert settings['ollama_model'] == 'two:latest'
    page.get_by_role('button', name='Test selected model').click()
    expect(page.get_by_role('status')).to_have_text('Model replied: Test model response')
    page.get_by_label('Backend-to-Ollama URL').fill('http://127.0.0.1:11435')
    expect(page.get_by_role('button', name='Test selected model')).to_be_disabled()
