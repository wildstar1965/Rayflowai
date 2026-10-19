import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.core.config import UPLOAD_DIR
from app.schemas.editing_plan import EditingPlan,ClipConfig,VisualInsert,SoundCue,SubtitleSegment,SubtitleStyle,WordTiming
from test_render_audit import run,render

def test_video_insert_uses_own_start_clock_and_clicks_export():
    base=UPLOAD_DIR/'creative_base.png';Image.new('RGB',(320,180),'black').save(base)
    insert=UPLOAD_DIR/'creative_change.mp4'
    run('-f','lavfi','-i','color=red:size=320x180:rate=30:duration=1',
        '-f','lavfi','-i','color=blue:size=320x180:rate=30:duration=1',
        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',insert)
    plan=EditingPlan(duration_seconds=4,aspect_ratio='16:9',title={'enabled':False},
        clips=[ClipConfig(id='main',image_url=str(base),start_time=0,duration=4,motion='static')],
        visual_inserts=[VisualInsert(id='video',asset_id='v',asset_url=str(insert),media_type='video',start_time=1.5,duration=2,mode='cutaway')],
        sound_cues=[SoundCue(id='a',label='one',start_time=.5,volume=.5),SoundCue(id='b',label='muted',start_time=1,muted=True),SoundCue(id='c',label='two',start_time=2,volume=.25)])
    output=render(plan,[str(base),str(insert)])
    frames=np.frombuffer(run('-i',output,'-vf','scale=16:9','-pix_fmt','rgb24','-f','rawvideo','-'),np.uint8).reshape(-1,9,16,3)
    assert len(frames)==120
    assert frames[50,:,:,0].mean()>180 and frames[50,:,:,2].mean()<60  # Insert's first second, not source time 1.5.
    assert frames[82,:,:,2].mean()>180
    assert frames[112].mean()<15
    pcm=np.frombuffer(run('-i',output,'-vn','-ar','48000','-ac','1','-f','f32le','-'),np.float32)
    energy=lambda begin,end:np.sqrt(np.mean(pcm[int(begin*48000):int(end*48000)]**2))
    assert energy(.5,.6)>.005 and energy(2,2.1)>.002
    assert energy(.98,1.13)<.001
    assert energy(.5,.6)>energy(2,2.1)*1.6
    assert abs(pcm).max()<.96

@pytest.mark.parametrize('ratio',['9:16','1:1','16:9'])
def test_cinematic_caption_raster_and_exact_frames(ratio):
    base=UPLOAD_DIR/'creative_caption.png';Image.new('RGB',(320,180),'#242424').save(base)
    plan=EditingPlan(duration_seconds=1,aspect_ratio=ratio,title={'enabled':False},
        clips=[ClipConfig(id='main',image_url=str(base),start_time=0,duration=1,motion='static')],
        subtitles=[SubtitleSegment(id='sub',text='Meaningful speech',start_time=.2,end_time=.8,style=SubtitleStyle(preset='cinematic',caption_mode='phrase',font_size=64),
                    words=[WordTiming(word='Meaningful',start=.2,end=.5),WordTiming(word='speech',start=.5,end=.8)])])
    output=render(plan,[str(base)])
    frames=np.frombuffer(run('-i',output,'-vf','scale=360:360','-pix_fmt','gray','-f','rawvideo','-'),np.uint8).reshape(-1,360,360)
    assert len(frames)==30
    assert frames[15,280:340,:].max()>170 and frames[2,280:340,:].max()<70
