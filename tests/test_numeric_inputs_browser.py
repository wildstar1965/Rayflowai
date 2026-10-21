"""Real keyboard regressions for numeric draft editing and studio integration."""
from test_studio_browser import local_servers, studio, plan, wait_plan
from playwright.sync_api import expect
import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def numeric(local_servers):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.goto(local_servers)
        page.evaluate("""async () => {
          const {default:React} = await import('/node_modules/.vite/deps/react.js');
          const {default:{createRoot}} = await import('/node_modules/.vite/deps/react-dom_client.js');
          const {NumericInput} = await import('/src/components/ui/NumericInput.tsx');
          const host=document.createElement('div');document.body.prepend(host);
          function Harness() {
            const [value,setValue]=React.useState(10);
            const [other,setOther]=React.useState(0);
            const [readOnly,setReadOnly]=React.useState(false);
            const [limits,setLimits]=React.useState({min:-2000,max:2000,step:.25});
            window.numericHarness={setValue,setOther,setLimits,setReadOnly};
            return React.createElement('div',null,
              React.createElement(NumericInput,{value,...limits,readOnly,'aria-label':'Test number',
                onCommit:next=>{window.commits.push(next);setValue(next)}}),
              React.createElement('output',{id:'committed'},String(value)),
              React.createElement('span',null,other));
          }
          window.commits=[];
          createRoot(host).render(React.createElement(Harness));
        }""")
        field=page.get_by_label('Test number')
        expect(field).to_have_value('10')
        yield page,field
        browser.close()


def test_shared_keyboard_drafts_cursor_delete_paste_and_sync(numeric):
    page,field=numeric
    for value in ['150','250','1250','999','1.5','0.25','-1.5','0']:
        previous=page.locator('#committed').inner_text()
        field.focus();field.press('Control+a');field.press('Backspace')
        expect(field).to_have_value('')
        for i,digit in enumerate(value):
            field.press_sequentially(digit)
            expect(field).to_have_value(value[:i+1])
            expect(page.locator('#committed')).to_have_text(previous)
        field.press('Enter');field.press('Tab')
        expect(field).to_have_value(value)
    assert page.evaluate('commits.length')==8  # Enter followed by blur is one edit.
    field.fill('150');field.press('Home');field.press('ArrowRight');field.press('Delete')
    field.press_sequentially('2')
    expect(field).to_have_value('120')
    assert field.evaluate('el=>el.selectionStart')==2
    page.evaluate('numericHarness.setOther(1)')
    expect(field).to_have_value('120')
    page.evaluate('numericHarness.setValue(7)')
    expect(field).to_have_value('120')
    field.press('Enter');expect(page.locator('#committed')).to_have_text('120')
    # Paste through the browser clipboard's native keyboard path.
    page.context.grant_permissions(['clipboard-read','clipboard-write'])
    page.evaluate("navigator.clipboard.writeText('42.25')")
    field.press('Control+a');field.press('Control+v')
    expect(field).to_have_value('42.25');field.press('Tab')
    expect(page.locator('#committed')).to_have_text('42.25')
    page.evaluate('numericHarness.setValue(18)')
    expect(field).to_have_value('18')


def test_shared_validation_boundaries_escape_and_step(numeric):
    page,field=numeric
    page.evaluate('numericHarness.setLimits({min:0,max:300,step:.25})')
    for typed,committed in [('0','0'),('300','300'),('-1','0'),('999','300'),('1.37','1.25')]:
        field.fill(typed);expect(field).to_have_value(typed)
        field.press('Enter');expect(field).to_have_value(committed)
    for invalid in ['', '-', '.', 'NaN', 'Infinity', '1x']:
        field.fill(invalid);field.press('Tab')
        expect(field).to_have_value('1.25')
        expect(page.locator('span[role=status]')).to_contain_text('previous value was kept')
    field.fill('22');field.press('Escape');expect(field).to_have_value('1.25')
    field.press('ArrowUp');expect(field).to_have_value('1.5')
    field.press('ArrowDown');expect(field).to_have_value('1.25')


def test_shared_step_grid_precision_and_read_only(numeric):
    page,field=numeric
    # A timing upper bound need not be on the field's step grid.
    page.evaluate('numericHarness.setLimits({min:.1,max:1.05,step:.1})')
    field.fill('1.05');field.press('Enter')
    expect(field).to_have_value('1')
    page.evaluate('numericHarness.setLimits({min:-.15,max:.26,step:.1})')
    field.fill('.26');field.press('Enter')
    expect(field).to_have_value('0.25')
    page.evaluate("numericHarness.setLimits({step:'any'})")
    field.fill('0.123456789012');field.press('Enter')
    expect(field).to_have_value('0.123456789012')
    page.evaluate('numericHarness.setLimits({step:.01})')
    field.fill('1e308');field.press('Enter')
    assert page.evaluate('commits.every(Number.isFinite)')
    page.evaluate('numericHarness.setReadOnly(true)')
    before=page.evaluate('commits.slice()')
    displayed=field.input_value()
    field.press('ArrowDown')
    expect(field).to_have_value(displayed)
    assert page.evaluate('commits')==before


def test_shared_arrow_keys_commit_as_one_edit(numeric):
    page,field=numeric
    field.focus()
    field.press('ArrowUp');field.press('ArrowUp');field.press('ArrowDown')
    expect(field).to_have_value('10.25')
    expect(page.locator('#committed')).to_have_text('10')
    assert page.evaluate('commits')==[]
    field.press('Tab')
    assert page.evaluate('commits')==[10.25]


def type_draft(field, text):
    field.focus();field.press('Control+a');field.press('Backspace')
    expect(field).to_have_value('')
    for index,digit in enumerate(text):
        field.press_sequentially(digit)
        expect(field).to_have_value(text[:index+1])


def test_caption_size_keeps_each_typed_digit(studio):
    page, errors = studio
    page.get_by_role('button', name='Captions', exact=False).click()
    page.get_by_role('button', name='+ Add Segment', exact=True).click()
    field = page.get_by_label('Caption font size', exact=True)
    field.fill('10')
    field.press('Tab')
    wait_plan(page, 'p.subtitles[0].style.font_size===10')
    field.focus();field.press('Control+a')
    for digit, expected in [('1','1'),('5','15'),('0','150')]:
        field.press_sequentially(digit)
        expect(field).to_have_value(expected)
        assert plan(page)['subtitles'][0]['style']['font_size']==10
    with page.expect_request(lambda r: '/api/cinematic/captions' in r.url and r.method == 'POST') as rendered:
        field.press('Enter')
    wait_plan(page, 'p.subtitles[0].style.font_size===150')
    assert rendered.value.post_data_json['subtitles'][0]['style']['font_size']==150
    page.get_by_role('button', name='Inserts', exact=False).click()
    page.get_by_role('button', name='Captions', exact=False).click()
    expect(page.get_by_label('Caption font size',exact=True)).to_have_value('150')
    page.get_by_title('Undo (Ctrl+Z)').click()
    wait_plan(page, 'p.subtitles[0].style.font_size===10')
    page.get_by_title('Redo',exact=True).click()
    wait_plan(page, 'p.subtitles[0].style.font_size===150')
    # Large drafts stay intact until commit, then respect the actual font limit.
    for typed,committed in [('250',250),('1250',300),('10',10),('999',300)]:
        previous=plan(page)['subtitles'][0]['style']['font_size']
        type_draft(field,typed)
        assert plan(page)['subtitles'][0]['style']['font_size']==previous
        field.press('Tab')
        wait_plan(page,f'p.subtitles[0].style.font_size==={committed}')
        expect(field).to_have_value(str(committed))
        page.get_by_title('Undo (Ctrl+Z)').click()
        wait_plan(page,f'p.subtitles[0].style.font_size==={previous}')
        page.get_by_title('Redo',exact=True).click()
        wait_plan(page,f'p.subtitles[0].style.font_size==={committed}')
    assert errors==[]


def test_caption_settings_preserve_draft_during_real_parent_updates(studio):
    page,errors=studio
    page.get_by_role('button',name='Captions',exact=False).click()
    page.get_by_role('button',name='+ Add Segment',exact=True).click()
    field=page.get_by_label('Caption font size',exact=True)
    field.fill('150');field.press('Home');field.press('ArrowRight');field.press('Delete')
    field.press_sequentially('2')
    expect(field).to_have_value('120')
    # Dispatch another setting's real React handler while keeping the field focused.
    page.get_by_label('Caption weight').evaluate("""el=>{
      el.value='400';el.dispatchEvent(new Event('change',{bubbles:true}));
    }""")
    wait_plan(page,'p.subtitles[0].style.font_weight===400')
    expect(field).to_be_focused();expect(field).to_have_value('120')
    assert field.evaluate('el=>el.selectionStart')==2
    page.get_by_role('button',name='Play',exact=True).evaluate('el=>el.click()')
    page.wait_for_function("Number(document.querySelector('[aria-label=\"Timeline playhead\"]').getAttribute('aria-valuenow'))>.15")
    expect(field).to_be_focused();expect(field).to_have_value('120')
    assert field.evaluate('el=>el.selectionStart')==2
    page.get_by_role('button',name='Pause',exact=True).evaluate('el=>el.click()')
    field.press('Enter')
    wait_plan(page,'p.subtitles[0].style.font_size===120 && p.subtitles[0].style.font_weight===400')
    page.get_by_title('Undo (Ctrl+Z)').click()
    wait_plan(page,'p.subtitles[0].style.font_size===42 && p.subtitles[0].style.font_weight===400')
    page.get_by_title('Redo',exact=True).click()
    wait_plan(page,'p.subtitles[0].style.font_size===120')
    field.fill('135')
    page.get_by_role('button',name='1:1',exact=True).click()
    wait_plan(page,"p.subtitles[0].style.font_size===135 && p.aspect_ratio==='1:1'")
    for label,typed,expression in [
        ('Caption tracking','-1.5','p.subtitles[0].style.tracking===-1.5'),
        ('Caption phrase length','75','p.subtitles[0].style.max_chars===75'),
        ('Caption phrase duration','1.5','p.subtitles[0].style.max_duration===1.5'),
        ('Caption backdrop opacity','60','p.subtitles[0].style.background_opacity===.6'),
        ('Caption backdrop opacity','0','p.subtitles[0].style.background_opacity===0'),
    ]:
        control=page.get_by_label(label,exact=True)
        type_draft(control,typed);control.press('Tab');wait_plan(page,expression)
    assert errors==[]


def test_creative_and_caption_timing_commit_boundaries(studio):
    page,errors=studio
    page.get_by_role('button',name='Inserts',exact=False).click()
    page.get_by_role('button',name='Add display text',exact=True).click()
    for label,typed,expression in [
        ('Cinematic size','150','p.cinematic_texts[0].font_size_ratio===.3'),
        ('Cinematic size','25','p.cinematic_texts[0].font_size_ratio===.25'),
        ('Cinematic tracking','-1.5','p.cinematic_texts[0].tracking===-1.5'),
        ('Cinematic horizontal position','75','p.cinematic_texts[0].x===.75'),
        ('Cinematic vertical position','15','p.cinematic_texts[0].y===.15'),
        ('Cinematic fade','0.25','p.cinematic_texts[0].animation_seconds===.25'),
        ('Cinematic entrance scale','95','p.cinematic_texts[0].scale_from===.95'),
        ('Cinematic start','1.5','p.cinematic_texts[0].start_time===1.5'),
        ('Cinematic duration','3.5','p.cinematic_texts[0].duration===3.5'),
    ]:
        field=page.get_by_label(label,exact=True)
        previous=plan(page)
        type_draft(field,typed)
        assert plan(page)==previous
        field.press('Tab');wait_plan(page,expression)
    page.get_by_role('button',name='Captions',exact=False).click()
    page.get_by_role('button',name='+ Add Segment',exact=True).click()
    start=page.get_by_label('Caption start',exact=True)
    start.fill('');expect(start).to_have_value('')
    start.press_sequentially('0.25');start.press('Enter')
    wait_plan(page,'p.subtitles[0].start_time===.25')
    page.get_by_title('Undo (Ctrl+Z)').click()
    wait_plan(page,'p.subtitles[0].start_time===0')
    expect(start).to_have_value('0')
    end=page.get_by_label('Caption end',exact=True)
    type_draft(end,'3.25');end.press('Tab')
    wait_plan(page,'p.subtitles[0].end_time===3.25')
    assert errors==[]


def test_broll_and_sound_numeric_fields_share_commit_behavior(studio):
    from test_studio_browser import KEY
    page,errors=studio
    page.evaluate("""key=>{
      const state=JSON.parse(localStorage.getItem(key));
      state.plan.visual_inserts=[{id:'numeric-insert',asset_id:'image',asset_url:state.images[1].url,
        start_time:1,duration:2,mode:'pip',position:'top_right',origin:'manual'}];
      state.plan.sound_cues=[{id:'numeric-cue',label:'camera',start_time:1,sound:'soft',volume:.3,muted:false}];
      localStorage.setItem(key,JSON.stringify(state));
    }""",KEY)
    page.reload();page.get_by_role('button',name='Open Studio',exact=True).first.click()
    page.get_by_role('button',name='Inserts',exact=False).click()
    for label,value,expression in [('Insert 1 start','1.5','p.visual_inserts[0].start_time===1.5'),
                                   ('Insert 1 duration','2.5','p.visual_inserts[0].duration===2.5'),
                                   ('Click 1 time','0.25','p.sound_cues[0].start_time===.25')]:
        field=page.get_by_label(label,exact=True)
        before=plan(page)
        field.fill('');expect(field).to_have_value('')
        field.press_sequentially(value);expect(field).to_have_value(value)
        assert plan(page)==before
        field.press('Enter');wait_plan(page,expression)
    page.get_by_label('Click 1 volume').fill('0')
    wait_plan(page,'p.sound_cues[0].volume===0')
    assert errors==[]


def test_numeric_project_setting_reaches_render_request_and_history(studio):
    page,errors=studio
    page.get_by_role('button',name='Pacing',exact=True).click()
    page.get_by_role('button',name='Cinematic',exact=False).click()
    field=page.get_by_label('Cinematic color strength',exact=True)
    type_draft(field,'150');field.press('Tab');expect(field).to_have_value('100')
    type_draft(field,'0');field.press('Tab')
    wait_plan(page,'p.color_strength===0')
    page.get_by_title('Undo (Ctrl+Z)').click()
    expect(field).to_have_value('100')
    page.get_by_title('Redo',exact=True).click()
    expect(field).to_have_value('0')
    # Capture the real export handler's payload without spending time encoding
    # another reel; the existing Studio browser suite checks MP4 completion.
    page.route('**/api/render',lambda route:route.fulfill(status=400,json={'detail':'Numeric test captured export'}))
    with page.expect_request(lambda r:r.url.endswith('/api/render') and r.method=='POST') as request:
        page.get_by_role('button',name='Export MP4',exact=True).click()
    assert request.value.post_data_json['plan']['color_strength']==0
    assert errors==[]
