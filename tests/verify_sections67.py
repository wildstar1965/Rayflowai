"""Opt-in local speech / moving-person / actual MP4 verification. No downloads."""
import copy
import json
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import FFMPEG_PATH,UPLOAD_DIR,EXPORT_DIR
from app.services.auto_edit import generate_auto_edit_reel
from app.services.speech_transcription import extract_audio_from_media,transcribe_audio_file
from app.services.segmentation import prepare_masks,mask_duration,existing_masks
from app.services.video_renderer import start_render_job,get_job_status
from app.services.cinematic import title_image
from app.schemas.editing_plan import CinematicText

ART=ROOT/'test_artifacts/sections67'
ART.mkdir(exist_ok=True)

def run(*args):
    result=subprocess.run([FFMPEG_PATH,'-v','error','-y',*map(str,args)],capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-1500:])
    return result.stdout

def render(plan,label):
    started=time.monotonic()
    job=start_render_job(plan,[plan.source_filename])
    deadline=started+240
    while time.monotonic()<deadline:
        state=get_job_status(job)
        if state.status in ('completed','failed'):
            assert state.status=='completed',state.error
            break
        time.sleep(.2)
    else:raise AssertionError('Export exceeded verification deadline')
    output=EXPORT_DIR/f'rayflow_{job}.mp4'
    target=ART/f'{label}.mp4'
    import shutil
    shutil.copyfile(output,target)
    run('-xerror','-i',target,'-f','null','-')
    return target,round(time.monotonic()-started,3)

def frame(path,time,width,height):
    raw=run('-ss',time,'-i',path,'-frames:v',1,'-vf',f'scale={width}:{height}','-f','rawvideo','-pix_fmt','rgb24','-')
    return np.frombuffer(raw,np.uint8).reshape(height,width,3).copy()

if __name__=='__main__':
    source=UPLOAD_DIR/'sections67_speaker.mp4'
    run('-i',sys.argv[1],'-t',4,'-c:v','libx264','-crf',18,'-pix_fmt','yuv420p','-c:a','aac',source)
    timings=[];start=time.monotonic()
    def report(stage):
        record={'seconds':round(time.monotonic()-start,3),'stage':stage};timings.append(record);print(json.dumps(record),flush=True)
    plan=generate_auto_edit_reel(source.name,style_key='cinematic',whisper_model='tiny',auto_broll=False,list_sounds=False,progress=report)
    assert plan.subtitles,plan.warnings
    assert any(s.words for s in plan.subtitles),'Local model did not return word timestamps'
    plan.cinematic_texts=[CinematicText(id='verify-title',text='SPEAK WITH\nIMPACT',source_clip_id=plan.clips[0].id,
        start_time=.2,duration=3.4,behind_subject=True,y=.18,emphasis_words=['IMPACT'])]
    timings_by_ratio=[]
    for ratio,w,h in [('9:16',1080,1920),('1:1',1080,1080),('16:9',1920,1080)]:
        plan.aspect_ratio=ratio
        manifest=prepare_masks(plan.clips[0],ratio,plan.fit_mode,mask_duration(plan,plan.clips[0]),progress=report)
        warm=time.monotonic();again=prepare_masks(plan.clips[0],ratio,plan.fit_mode,mask_duration(plan,plan.clips[0]));warm=time.monotonic()-warm
        assert manifest==again
        label=ratio.replace(':','x')
        path,seconds=render(plan,label)
        raw=run('-i',path,'-vf','scale=16:16','-f','rawvideo','-pix_fmt','rgb24','-')
        assert len(raw)//(16*16*3)==120
        pcm=np.frombuffer(run('-i',path,'-vn','-ar',16000,'-ac',1,'-f','f32le','-'),np.float32)
        assert np.sqrt(np.mean(pcm**2))>.001
        actual=frame(path,1,w,h)
        Image.fromarray(actual).save(ART/f'{label}-export.png')
        if ratio=='9:16':
            (ART/'plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf8')
            baseline=plan.model_copy(deep=True);baseline.cinematic_texts=[];baseline.subtitles=[]
            base_path,_=render(baseline,'base')
            base=frame(base_path,1,w,h)
            front=plan.model_copy(deep=True);front.cinematic_texts[0].behind_subject=False;front.subtitles=[]
            front_path,_=render(front,'unmasked-control')
            unmasked=frame(front_path,1,w,h)
            directory=existing_masks(plan.clips[0],ratio,plan.fit_mode,mask_duration(plan,plan.clips[0]))
            matte=np.asarray(Image.open(directory/'00030.png').resize((w,h),Image.Resampling.BILINEAR))
            title=plan.cinematic_texts[0]
            alpha=np.asarray(Image.open(title_image(title.text,title.color,w,h,title)).getchannel('A'))
            subject=(matte>250)&(alpha>250)
            background=(matte<5)&(alpha>250)
            assert subject.sum()>500 and background.sum()>500
            diff=np.abs(actual.astype(float)-base.astype(float)).mean(axis=2)
            control=np.abs(unmasked.astype(float)-base.astype(float)).mean(axis=2)
            assert diff[subject].mean()<control[subject].mean()*.15,(diff[subject].mean(),control[subject].mean())
            assert diff[background].mean()>20
            assert np.abs(np.asarray(Image.open(directory/'00005.png')).astype(float)-np.asarray(Image.open(directory/'00070.png')).astype(float)).mean()>1
            Image.fromarray(matte).save(ART/'subject-mask.png')
            sheet=Image.new('RGB',(1080,640))
            for i,im in enumerate([base,unmasked,actual]):sheet.paste(Image.fromarray(im).resize((360,640)),(i*360,0))
            sheet.save(ART/'occlusion-comparison.png')
            occlusion={'subject_pixels':int(subject.sum()),'background_pixels':int(background.sum()),'subject_error':round(float(diff[subject].mean()),3),'unmasked_error':round(float(control[subject].mean()),3)}
        timings_by_ratio.append({'ratio':ratio,'mask_seconds':manifest['elapsed_seconds'],'mask_cache_seconds':round(warm,4),'export_seconds':seconds,'frames':120,'audio_rms':round(float(np.sqrt(np.mean(pcm**2))),4)})
    wav=ART/'speech.wav';extract_audio_from_media(str(source),str(wav))
    started=time.monotonic();transcribe_audio_file(str(wav),'tiny');cached=time.monotonic()-started
    result={'transcript':[s.model_dump() for s in plan.subtitles],'stages':timings,'renders':timings_by_ratio,'occlusion':occlusion,'transcript_cache_seconds':round(cached,4),'full_decode':True}
    (ART/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result),flush=True)
