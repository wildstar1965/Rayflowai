"""Opt-in preview comparison against the real, unmodified Auto Reel output."""
import base64
import io
import json
import subprocess
import sys
import numpy as np
from PIL import Image
import pytest
from test_studio_browser import ROOT, KEY, local_servers, studio, wait_plan


def test_generated_reel_preview_matches_export(studio):
    artifact=ROOT/'test_artifacts/reel-quality'
    if not (artifact/'after.mp4').exists():pytest.skip('Run verify_reel_quality.py with actual source footage first.')
    generated=json.loads((artifact/'after-plan.json').read_text())
    page,errors=studio
    page.evaluate("""({key,plan})=>{
      const state=JSON.parse(localStorage.getItem(key));state.plan=plan;
      state.images=[{filename:plan.source_filename,original_name:'Quality source.mp4',url:plan.clips[0].image_url,media_type:'video',size:1}];
      localStorage.setItem(key,JSON.stringify(state));
    }""",{'key':KEY,'plan':generated})
    page.reload();page.get_by_role('button',name='Open Studio',exact=True).first.click()
    wait_plan(page,'p.source_filename === "quality_speaker.mp4"')
    sys.path.insert(0,str(ROOT/'backend'))
    from app.core.config import FFMPEG_PATH
    head=page.get_by_role('slider',name='Timeline playhead')
    comparisons=[]
    for t in [4,9]:
        head.focus();head.press('Home')
        for _ in range(t):head.press('Shift+ArrowRight')
        page.wait_for_timeout(1200)
        data=page.locator('main canvas').evaluate('c=>({width:c.width,height:c.height,png:c.toDataURL()})')
        actual=np.asarray(Image.open(io.BytesIO(base64.b64decode(data['png'].split(',')[1]))).convert('RGB')).astype(float)
        raw=subprocess.check_output([FFMPEG_PATH,'-v','error','-ss',str(t),'-i',str(artifact/'after.mp4'),'-frames:v','1',
            '-vf',f"scale={data['width']}:{data['height']}",'-f','rawvideo','-pix_fmt','rgb24','-'])
        exported=np.frombuffer(raw,np.uint8).reshape(data['height'],data['width'],3).astype(float)
        difference=float(np.abs(actual-exported).mean())
        comparisons.append({'seconds':t,'mean_rgb_error':difference})
        assert difference<12,comparisons
        page.locator('main canvas').screenshot(path=str(artifact/f'preview-{t}s.png'))
    page.get_by_role('button',name='Play',exact=True).click();page.wait_for_timeout(400)
    page.get_by_role('button',name='Pause',exact=True).click()
    assert float(head.get_attribute('aria-valuenow'))>9.2
    (artifact/'preview-comparison.json').write_text(json.dumps(comparisons,indent=2))
    assert errors==[]
