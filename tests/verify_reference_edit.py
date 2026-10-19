"""Local reference-based speech/matte/export verification; no publishing."""
import json
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.core.config import FFMPEG_PATH,UPLOAD_DIR,EXPORT_DIR,CACHE_DIR
from app.services.auto_edit import generate_auto_edit_reel
from app.services.video_renderer import start_render_job,get_job_status
from app.services.segmentation import existing_masks,mask_duration
from app.schemas.editing_plan import SoundCue

if __name__=='__main__':
    reference=Path(sys.argv[1])
    source=UPLOAD_DIR/'reference_speech_test.mp4'
    subprocess.run([FFMPEG_PATH,'-v','error','-y','-ss','37','-i',str(reference),'-t','4',
                    '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    start=time.monotonic()
    timings=[]
    def report(stage):
        record={'seconds':round(time.monotonic()-start,2),'stage':stage};timings.append(record);print(json.dumps(record),flush=True)
    plan=generate_auto_edit_reel(source.name,style_key='cinematic',whisper_model='tiny',auto_broll=False,list_sounds=True,progress=report)
    assert plan.subtitles,plan.warnings
    assert plan.cinematic_texts and plan.cinematic_texts[0].behind_subject,plan.warnings
    directory=existing_masks(plan.clips[0],plan.aspect_ratio,plan.fit_mode,mask_duration(plan,plan.clips[0]))
    frame=np.asarray(Image.open(directory/'00010.png'))
    assert frame.max()>240 and frame.min()<10 and (frame>128).mean()>.05
    # Explicit test cue checks the final audio mix independently of the speech content.
    plan.sound_cues=[SoundCue(id='verification-cue',label='Export audio verification',start_time=.5)]
    Path('test_artifacts/reference-edit-plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf8')
    job=start_render_job(plan,[source.name])
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        status=get_job_status(job)
        if status.status in ('completed','failed'):
            assert status.status=='completed',status.error
            break
        time.sleep(.2)
    else:raise AssertionError('Reference export exceeded 120 seconds')
    output=EXPORT_DIR/f'rayflow_{job}.mp4'
    decoded=subprocess.run([FFMPEG_PATH,'-v','error','-xerror','-i',str(output),'-f','null','-'],capture_output=True)
    assert decoded.returncode==0,decoded.stderr
    for label,path,at in [('source',source,1),('export',output,1)]:
        subprocess.run([FFMPEG_PATH,'-v','error','-y','-ss',str(at),'-i',str(path),'-frames:v','1',f'test_artifacts/reference-{label}.png'],check=True)
    record={'output':str(output),'transcript':[s.text for s in plan.subtitles],'timings':timings,'matte_frames':len(list(directory.glob('[0-9][0-9][0-9][0-9][0-9].png'))),'full_decode':True}
    Path('test_artifacts/reference-verification.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps(record),flush=True)
