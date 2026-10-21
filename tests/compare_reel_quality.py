"""Compare saved Auto Reel artifacts at corresponding source times; render controls."""
import json
from pathlib import Path
import sys
import numpy as np
from scipy.signal import correlate
from PIL import Image, ImageDraw

from verify_reel_quality import ART,ROOT,ffmpeg,render,inspect
from app.schemas.editing_plan import EditingPlan
from app.services.cinematic import title_image
from app.services.segmentation import existing_masks,mask_duration


def frame(path,t,width=1080,height=1920):
    return np.frombuffer(ffmpeg('-ss',t,'-i',path,'-frames:v',1,'-vf',f'scale={width}:{height}',
                               '-f','rawvideo','-pix_fmt','rgb24','-'),np.uint8).reshape(height,width,3)


if __name__=='__main__':
    plan=EditingPlan.model_validate_json((ART/'after-plan.json').read_text())
    baseline=EditingPlan.model_validate_json((ART/'before-plan.json').read_text())
    base=plan.model_copy(deep=True);base.cinematic_texts=[];base.subtitles=[]
    if '--reuse-controls' not in sys.argv:render(base,'after-base')
    control=plan.model_copy(deep=True)
    for title in control.cinematic_texts:title.behind_subject=False
    if '--reuse-controls' not in sys.argv:render(control,'after-unmasked')
    samples=[.85,4,6,9.7,12.8,14.5]
    sheet=Image.new('RGB',(360*len(samples),350*2),'#222222');draw=ImageDraw.Draw(sheet)
    # Columns compare the same source moment, accounting for the new source trims.
    mapped=[]
    for i,source_time in enumerate(samples):
        times=[]
        for row,(label,p) in enumerate([('before',baseline),('after',plan)]):
            clip=next(c for c in p.clips if c.source_start<=source_time<c.source_start+c.duration)
            t=round((clip.start_time+source_time-clip.source_start)*30)/30
            times.append(t)
            im=Image.fromarray(frame(ART/f'{label}.mp4',t,180,320))
            # Two images per column, vertically aligned, with source and timeline labels.
            sheet.paste(im,(i*360+90,row*350))
            draw.text((i*360+10,row*350+323),f'{label}: source {source_time:.2f}s / edit {t:.2f}s',fill='white')
        mapped.append({'source':source_time,'before':times[0],'after':times[1]})
    sheet.save(ART/'before-after.png')
    title=next(t for t in plan.cinematic_texts if t.behind_subject)
    clip=next(c for c in plan.clips if c.id==title.source_clip_id)
    t=round((title.start_time+title.duration*.55)*30)/30
    actual=frame(ART/'after.mp4',t).astype(float)
    base_pixels=frame(ART/'after-base.mp4',t).astype(float)
    front=frame(ART/'after-unmasked.mp4',t).astype(float)
    masks=existing_masks(clip,plan.aspect_ratio,plan.fit_mode,mask_duration(plan,clip))
    matte=np.asarray(Image.open(masks/f'{round((t-clip.start_time)*30):05d}.png').resize((1080,1920)))
    alpha=np.asarray(Image.open(title_image(title.text,title.color,1080,1920,title,round((t-title.start_time)*30))).getchannel('A'))
    subject=(matte>245)&(alpha>240);background=(matte<5)&(alpha>240)
    masked_error=np.abs(actual-base_pixels).mean(axis=2)
    front_error=np.abs(front-base_pixels).mean(axis=2)
    occlusion={'time':t,'subject_pixels':int(subject.sum()),'background_pixels':int(background.sum()),
               'masked_subject_error':float(masked_error[subject].mean()),'unmasked_subject_error':float(front_error[subject].mean()),
               'background_title_error':float(masked_error[background].mean())}
    assert subject.sum()>100 and background.sum()>500
    assert occlusion['masked_subject_error']<occlusion['unmasked_subject_error']*.4,occlusion
    occlusion_sheet=Image.new('RGB',(1080,640))
    for i,pixels in enumerate([base_pixels,front,actual]):occlusion_sheet.paste(Image.fromarray(pixels.astype(np.uint8)).resize((360,640)),(360*i,0))
    occlusion_sheet.save(ART/'actual-occlusion.png')
    def audio(path):return np.frombuffer(ffmpeg('-i',path,'-vn','-ac',1,'-ar',48000,'-f','f32le','-'),np.float32)
    original=audio(ROOT/'backend/storage/uploads'/plan.source_filename);actual_audio=audio(ART/'after.mp4')
    correlations=[];alignment=[];clip_offsets={}
    for clip in plan.clips:
        for offset in [1,3,5]:
            if offset+.3>clip.duration:continue
            a=round((clip.start_time+offset)*48000);b=round((clip.source_start+offset)*48000)
            window=actual_audio[a:a+14400]
            search=original[b-2400:b+14400+2400]
            offset=int(correlate(search,window,mode='valid',method='fft').argmax())-2400
            correlation=float(np.corrcoef(window,original[b+offset:b+offset+14400])[0,1])
            correlations.append(correlation)
            alignment.append({'timeline':clip.start_time+offset/48000,'source_offset_samples':offset,'offset_ms':offset/48,'correlation':correlation})
            clip_offsets[clip.id]=offset
    assert min(correlations)>.97,correlations
    assert max(abs(row['offset_ms']) for row in alignment)<20,alignment
    cues=[]
    for cue in plan.sound_cues:
        clip=next(c for c in plan.clips if c.start_time<=cue.start_time<c.start_time+c.duration)
        a=round(cue.start_time*48000);b=round((clip.source_start+cue.start_time-clip.start_time)*48000)+clip_offsets[clip.id]
        residual=actual_audio[a:a+4800]-original[b:b+4800]
        cues.append({'label':cue.label,'time':cue.start_time,'volume':cue.volume,'residual_rms':float(np.sqrt(np.mean(residual**2)))})
    result={'source_aligned_frames':mapped,'occlusion':occlusion,'speech_audio_alignment':alignment,'sound_cues':cues,
            'before':inspect(ART/'before.mp4','before'),'after':inspect(ART/'after.mp4','after')}
    (ART/'comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
