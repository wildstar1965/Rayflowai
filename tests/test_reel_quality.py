"""Editorial safety, shared layout and source-clock export regressions."""
import json
from pathlib import Path
import subprocess
import sys
import time
import wave
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.schemas.editing_plan import EditingPlan, ClipConfig, SubtitleSegment, SubtitleStyle, WordTiming, CinematicText
from app.services.speech_edit import speech_clips, quiet_windows
from app.services.caption_frames import attach_transcript, _paint
from app.services.cinematic import suggest_cinematic_texts, place_title_with_mattes, _paint_title
from app.services.list_sounds import detect_list_items


def segment(text,times,identity='s'):
    words=[WordTiming(word=word,start=start,end=end) for word,(start,end) in zip(text.split(),times)]
    return SubtitleSegment(id=identity,text=text,start_time=words[0].start,end_time=words[-1].end,words=words)


def speech_fixture():
    return [segment('Hi, I build useful tools.',[(.1,.3),(.6,.8),(.8,1.1),(1.2,1.5),(1.5,1.8)]),
            segment('They help people.',[(3.5,3.8),(3.9,4.2),(4.3,4.6)],'s2')]


def test_trims_preserve_every_content_word_and_source_clock():
    segments=speech_fixture()
    clips=speech_clips('speaker.mp4',6,segments,[(1.8,3.5),(4.6,6)])
    assert len(clips)==2 and clips[0].source_start==pytest.approx(.4666666667)
    assert clips[0].duration*30==pytest.approx(round(clips[0].duration*30))
    plan=EditingPlan(duration_seconds=sum(c.duration for c in clips),clips=clips)
    mapped=attach_transcript(segments,plan,'speaker.mp4')
    assert ' '.join(s.text for s in mapped)=='I build useful tools. They help people.'
    for s in mapped:
        clip=next(c for c in clips if c.id==s.source_clip_id)
        original=next(x for x in segments if s.id.endswith('-'+x.id))
        for word in s.words:
            source=next(w for w in original.words if w.word==word.word)
            assert word.start-clip.start_time+clip.source_start==pytest.approx(source.start)
    assert clips[1].start_time==clips[0].duration
    assert clips[-1].source_start+clips[-1].duration>=4.9


def test_loud_pauses_partial_transcripts_and_short_pauses_are_retained():
    segments=speech_fixture()
    assert len(speech_clips('s.mp4',6,segments,[]))==1
    segments[0].words=[]
    clips=speech_clips('s.mp4',6,segments,[(0,6)])
    assert clips[0].source_start==0 and clips[0].duration==6
    segments=speech_fixture();segments[0].text='Manually corrected text.'
    assert speech_clips('s.mp4',6,segments,[(0,6)])[0].source_start==0


def test_room_tone_detection_requires_speech_separation(tmp_path):
    rate=16000;t=np.arange(rate*4)/rate
    samples=.012*np.sin(2*np.pi*120*t)
    samples[:rate*2]+=.15*np.sin(2*np.pi*440*t[:rate*2])
    path=tmp_path/'speech.wav'
    with wave.open(str(path),'wb') as wav:
        wav.setparams((1,2,rate,0,'NONE','not compressed'));wav.writeframes((samples*32767).astype('<i2').tobytes())
    quiet=quiet_windows(path)
    assert sum(b-a for a,b in quiet if a>=2)>1.8
    assert sum(b-a for a,b in quiet if a<2)<.1


def test_titles_are_complete_phrases_and_keep_negation():
    seg=segment('Coming to my technical experiences, I worked on various fields across hardware, software and AI.',
                [(i*.4,(i+1)*.4) for i in range(16)])
    plan=EditingPlan(duration_seconds=8,clips=[ClipConfig(id='c',image_url='s.mp4',duration=8,start_time=0)],subtitles=[seg])
    texts=[t.text.replace('\n',' ') for t in suggest_cinematic_texts(plan)]
    assert texts[0]=='technical experiences'
    assert 'software and AI' not in texts
    negative=segment('Never stop learning.',[(0,.5),(.5,1),(1,1.6)])
    plan.subtitles=[negative]
    assert suggest_cinematic_texts(plan)[0].text.replace('\n',' ')=='Never stop learning'


def test_safe_caption_backdrop_and_bounded_subject_overlap():
    style=SubtitleStyle(font_size=46,safe_area=True,background_opacity=.62)
    image=_paint([{'word':'Clear captions'}],style,1080,1920)
    bounds=image.getbbox()
    assert bounds[0]>=70 and bounds[2]<=1010 and bounds[3]<1920*.84
    assert 150 in np.unique(np.asarray(image.getchannel('A'))) or 158 in np.unique(np.asarray(image.getchannel('A')))
    matte=Image.new('L',(270,480));matte.paste(255,(90,130,180,480))
    title=CinematicText(id='t',text='TELL YOUR\nSTORY',start_time=0,duration=2,source_clip_id='c')
    place_title_with_mattes(title,[matte,matte])
    alpha=np.asarray(_paint_title(title,270,480).getchannel('A'),float)
    overlap=(alpha*(np.asarray(matte)/255)).sum()/alpha.sum()
    assert 0<overlap<=.28 and title.behind_subject


def test_spoken_fields_list_has_three_genuine_word_onsets():
    seg=segment('I worked in fields across hardware, software and AI.',[(i*.4,(i+1)*.4) for i in range(10)])
    items=detect_list_items([seg])
    assert [label for _,label in items]==['hardware','software','AI']
    assert [start for start,_ in items]==pytest.approx([2,2.4,3.2])


def test_actual_trimmed_mp4_keeps_source_audio_and_frame_count(tmp_path,monkeypatch):
    from app.core.config import FFMPEG_PATH
    from app.services import video_renderer,media
    source=tmp_path/'speaker.mp4'
    subprocess.run([FFMPEG_PATH,'-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=6',
        '-f','lavfi','-i',"aevalsrc=0.2*sin(2*PI*(200*t+35*t*t)):s=48000:d=6",'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    clips=speech_clips(source.name,6,speech_fixture(),[(1.8,3.5),(4.6,6)])
    for c in clips:c.image_url=str(source)
    monkeypatch.setattr(video_renderer,'EXPORT_DIR',tmp_path)
    plan=EditingPlan(duration_seconds=sum(c.duration for c in clips),aspect_ratio='16:9',clips=clips,color_strength=0,title={'enabled':False})
    job=video_renderer.start_render_job(plan,[str(source)])
    deadline=time.monotonic()+90
    while video_renderer.get_job_status(job).status not in ('completed','failed') and time.monotonic()<deadline:time.sleep(.1)
    state=video_renderer.get_job_status(job)
    assert state.status=='completed',state.error
    path=tmp_path/f'rayflow_{job}.mp4'
    def audio(path):
        return np.frombuffer(subprocess.check_output([FFMPEG_PATH,'-v','error','-i',str(path),'-vn','-ar','48000','-ac','1','-f','f32le','-']),np.float32)
    actual,original=audio(path),audio(source)
    for c in clips:
        at=round((c.start_time+.15)*48000);source_at=round((c.source_start+.15)*48000)
        assert np.corrcoef(actual[at:at+12000],original[source_at:source_at+12000])[0,1]>.98
    raw=subprocess.check_output([FFMPEG_PATH,'-v','error','-xerror','-i',str(path),'-vf','scale=2:2','-f','rawvideo','-pix_fmt','gray','-'])
    assert len(raw)//4==round(plan.duration_seconds*30)
