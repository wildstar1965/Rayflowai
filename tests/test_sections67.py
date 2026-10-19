"""Deterministic speech, typography, cache and matte regressions; no model downloads."""
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.schemas.editing_plan import EditingPlan, ClipConfig, SubtitleSegment, SubtitleStyle, WordTiming, CinematicText
from app.services import cinematic, caption_frames, speech_transcription as speech, segmentation
from app.services.processing import ProcessingCancelled
from fastapi.testclient import TestClient
from app.main import app


def segment(text='Hello world.', start=0, end=2, words=None, **style):
    return SubtitleSegment(id='s', text=text, start_time=start, end_time=end,
                           words=words or [], style=SubtitleStyle(preset='cinematic', caption_mode='phrase', **style))


@pytest.fixture
def raster_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cinematic, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(caption_frames, 'CACHE_DIR', tmp_path)
    return tmp_path


@pytest.mark.parametrize('dimensions', [(1080,1920),(1080,1080),(1920,1080)])
def test_title_style_safe_margins_animation_and_export_track(raster_cache, dimensions):
    w,h = dimensions
    title = CinematicText(id='t',text='YOUR\nSTORY',source_clip_id='c',start_time=.4,duration=1,
                          tracking=2,emphasis_words=['STORY'],x=.95,y=.85)
    path = cinematic.title_image(title.text,title.color,w,h,title)
    with Image.open(path) as image:
        left,top,right,bottom = image.getbbox()
        assert left >= w*.05-3 and right <= w*.95+3 and bottom < h*.96 and top > 0
        assert image.size == dimensions
    assert cinematic.animation_state(title,0)[0] == 0
    assert cinematic.animation_state(title,10) == (1,1)
    assert 0 < cinematic.animation_state(title,29)[0] < 1
    track = cinematic.title_track(title,w,h,raster_cache/'title.ffconcat')
    assert 'option framerate 30' in Path(track).read_text()
    assert len(list(raster_cache.glob('type_*.png'))) < 20
    response = TestClient(app).post('/api/cinematic/titles',json={'aspect_ratio':{1080:'9:16'}.get(w,'16:9') if w!=h else '1:1','cinematic_texts':[title.model_dump()]})
    assert response.status_code == 200
    assert len(response.json()[0]['frames']) == 30
    assert response.json()[0]['frames'][10].endswith(path.stem[5:]+'.png')


def test_font_fallback_and_real_weight():
    assert cinematic.local_font(40,'missing font').getlength('Hello') > 0
    assert cinematic.local_font(40,'Arial',400).getlength('Hello') != cinematic.local_font(40,'Arial',700).getlength('Hello')


def test_auto_display_text_skips_short_greetings():
    plan=EditingPlan(duration_seconds=5,clips=[ClipConfig(id='c',image_url='speaker.mp4',start_time=0,duration=5)],
                     subtitles=[segment('Hi.',end=.3),segment('Hello, my name is Sam.',start=.4,end=1.5)])
    assert cinematic.suggest_cinematic_texts(plan)==[]
    plan.subtitles.append(segment('Practice makes real progress.',start=1.5,end=4))
    titles=cinematic.suggest_cinematic_texts(plan)
    assert len(titles)==1 and titles[0].text=='Practice makes real progress' and titles[0].start_time==1.5


def test_phrase_punctuation_gaps_and_honest_fallback(raster_cache):
    words=[WordTiming(word='Hello',start=.1,end=.4),WordTiming(word='world.',start=.6,end=.9),
           WordTiming(word='Next!',start=1.2,end=1.5)]
    sub=segment('Hello world. Next!',end=2,words=words)
    units=caption_frames.caption_units(sub,2)
    assert [(u[0],u[1]) for u in units]==[(0,1.2),(1.2,2)]
    assert [w['word'] for w in units[0][2]]==['Hello','world.']
    sub.text='A manually corrected sentence with more words.'
    units=caption_frames.caption_units(sub,2)
    assert len(units)==1 and units[0][0:2]==(0,2)
    assert units[0][2][0]['word']==sub.text


def test_abbreviations_and_joined_tokens_keep_real_timing():
    sub=segment("Mr. Smith studies B-tech.",end=3,words=[WordTiming(word=w,start=i*.4,end=(i+1)*.4)
        for i,w in enumerate(['Mr.','Smith','studies','B','-tech.'])])
    units=caption_frames.caption_units(sub,3)
    assert len(units)==1 and units[0][2][-1]['join_left']
    assert units[0][2][-1]['start']==1.6


def test_word_highlights_overlap_and_line_breaks(raster_cache):
    sub=segment('Hello\nworld.',words=[WordTiming(word='Hello',start=0,end=.5),WordTiming(word='world.',start=.8,end=1.5)],highlight_active=True)
    events=caption_frames.caption_events([sub,segment('Next.',start=1.7,end=3)],1080,1920)
    assert all(a['end_time']<=b['start_time'] for a,b in zip(events,events[1:]))
    assert len({e['path'] for e in events})>=3
    assert caption_frames.caption_units(sub,2)[0][2][1]['line_before']


@pytest.mark.parametrize('dimensions',[(1080,1920),(1080,1080),(1920,1080)])
def test_long_caption_fits_all_ratios(raster_cache,dimensions):
    sub=segment('A very long corrected sentence that must wrap safely. '+('W'*80),font_size=120)
    event=caption_frames.caption_events([sub],*dimensions)[0]
    with Image.open(event['path']) as image:
        l,t,r,b=image.getbbox();w,h=dimensions
        assert l>=w*.075 and r<=w*.925 and 0<t<b<h


def test_trimmed_repeated_source_alignment():
    plan=EditingPlan(duration_seconds=8,clips=[ClipConfig(id='a',image_url='/api/uploads/source.mp4',media_type='video',start_time=0,duration=2,source_start=5),
        ClipConfig(id='b',image_url='/api/uploads/source.mp4',media_type='video',start_time=4,duration=3,source_start=4)])
    sub=segment('Hello world.',start=4.5,end=6,words=[WordTiming(word='Hello',start=4.5,end=5),WordTiming(word='world.',start=5,end=6)])
    result=caption_frames.attach_transcript([sub],plan,'source.mp4')
    assert [(s.start_time,s.end_time,s.text,s.source_clip_id) for s in result]==[(0,1,'world.','a'),(4.5,6,'Hello world.','b')]
    assert result[0].words[0].start==0


def test_real_model_metadata_validation_and_segment_fallback(monkeypatch):
    model=Mock()
    model.transcribe.return_value=(iter([SimpleNamespace(start=0,end=1,text='Hello.',words=[SimpleNamespace(word='Hello.',start=0,end=.8)]),
                                         SimpleNamespace(start=.9,end=2,text='Phrase only.',words=None)]),None)
    monkeypatch.setattr(speech,'_model',lambda *args:model)
    result=speech._transcribe_uncached('unused','tiny','en')
    assert result[0].words[0].end==.8 and result[1].start_time==1 and result[1].words==[]
    assert model.transcribe.call_args.kwargs['language']=='en'


def test_cache_cancel_and_native_error_redaction(tmp_path,monkeypatch):
    monkeypatch.setattr(speech,'CACHE_DIR',tmp_path)
    path=tmp_path/'a.wav';path.write_bytes(b'audio')
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(ProcessingCancelled):speech.transcribe_audio_file(str(path),cancel=cancelled)
    monkeypatch.setattr(speech,'_transcribe_uncached',Mock(side_effect=RuntimeError('secret-path')))
    with pytest.raises(speech.TranscriptionError) as error:speech.transcribe_audio_file(str(path))
    assert 'secret-path' not in str(error.value) and not list(tmp_path.glob('transcript*'))


def test_missing_model_setup_message(monkeypatch):
    import faster_whisper
    speech._model.cache_clear()
    monkeypatch.setattr(faster_whisper,'WhisperModel',Mock(side_effect=OSError('private directory')))
    with pytest.raises(speech.TranscriptionError,match='setup_local_assets.py --whisper') as error:speech._model('missing')
    assert 'private directory' not in str(error.value)
    speech._model.cache_clear()


def test_cancel_transcription_worker_cleans_extraction(tmp_path,monkeypatch):
    monkeypatch.setattr(speech,'UPLOAD_DIR',tmp_path)
    (tmp_path/'source.mp4').write_bytes(b'source')
    job='test-cancel';speech._TRANSCRIPTION_JOBS[job]={'status':'queued'}
    cancel=threading.Event();speech._CANCEL_EVENTS[job]=cancel
    def extract(source,target,cancel=None):
        Path(target).write_bytes(b'wav')
        cancel.set()
        raise ProcessingCancelled()
    monkeypatch.setattr(speech,'extract_audio_from_media',extract)
    speech._transcription_worker(job,'source.mp4','tiny')
    assert speech._TRANSCRIPTION_JOBS.pop(job)['status']=='cancelled'
    assert not list(tmp_path.glob('temp_*.wav'))


def test_mask_failure_cleans_work_directory(tmp_path,monkeypatch):
    monkeypatch.setattr(segmentation,'CACHE_DIR',tmp_path)
    source=tmp_path/'source.mp4';source.write_bytes(b'video')
    model=tmp_path/'model.onnx';model.write_bytes(b'model')
    monkeypatch.setattr(segmentation,'model_path',lambda:model)
    monkeypatch.setattr(segmentation,'uploaded_path',lambda _:source)
    monkeypatch.setattr(segmentation,'availability',lambda:{'available':True})
    monkeypatch.setattr(segmentation,'probe_media',lambda _:{'width':0,'height':0})
    clip=ClipConfig(id='c',image_url='source.mp4',start_time=0,duration=1,media_type='video')
    with pytest.raises(ValueError,match='dimensions'):segmentation.prepare_masks(clip,'9:16','fill')
    assert not list(tmp_path.glob('matte*'))
    cancel=threading.Event();cancel.set()
    with pytest.raises(ProcessingCancelled):segmentation.prepare_masks(clip,'9:16','fill',cancel=cancel)


def test_mask_configuration_invalidates_cache(tmp_path,monkeypatch):
    source=tmp_path/'s.mp4';source.write_bytes(b'x')
    monkeypatch.setattr(segmentation,'uploaded_path',lambda _:source)
    clip=ClipConfig(id='c',image_url='s.mp4',start_time=0,duration=2)
    key=segmentation.mask_key(clip,'9:16','fill')
    monkeypatch.setenv('PERSON_MASK_MAX_SIDE','720')
    assert segmentation.mask_key(clip,'9:16','fill')!=key


def test_invalid_subtitle_timing_and_title_config():
    with pytest.raises(ValueError):segment(start=2,end=1)
    with pytest.raises(ValueError):CinematicText(id='t',text='x',source_clip_id='c',start_time=0,duration=1,color='red')


def test_actual_frame_alignment_and_native_mask_reuse(tmp_path,monkeypatch):
    import subprocess
    from app.core.config import FFMPEG_PATH
    source=tmp_path/'two-colors.mp4'
    subprocess.run([FFMPEG_PATH,'-v','error','-y','-f','lavfi','-i','color=red:s=64x64:r=30:d=0.2',
                    '-f','lavfi','-i','color=blue:s=64x64:r=30:d=0.2','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
                    '-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    monkeypatch.setattr(segmentation,'CACHE_DIR',tmp_path)
    monkeypatch.setattr(segmentation,'uploaded_path',lambda _:source)
    model=tmp_path/'rvm.onnx';model.write_bytes(b'test')
    monkeypatch.setattr(segmentation,'model_path',lambda:model)
    monkeypatch.setattr(segmentation,'availability',lambda:{'available':True})
    monkeypatch.setenv('PERSON_INFERENCE_MAX_SIDE','320')
    monkeypatch.setenv('PERSON_MASK_MAX_SIDE','320')
    session=Mock();session.get_inputs.return_value=[SimpleNamespace(name='src')]
    def predict(_,inputs):
        src=inputs['src'];alpha=(src[:,0:1]>src[:,2:3]).astype(np.float32)
        return [src,alpha,*[np.zeros((1,1,1,1),np.float32) for _ in range(4)]]
    session.run.side_effect=predict
    monkeypatch.setattr(segmentation,'_session',lambda *args:session)
    clip=ClipConfig(id='c',image_url=source.name,media_type='video',start_time=0,duration=.4)
    result=segmentation.prepare_masks(clip,'9:16','fill')
    assert result['fps']==30 and result['frames']==12 and session.run.call_count==12
    directory=tmp_path/f"matte_{result['key']}"
    assert np.asarray(Image.open(directory/'00000.png')).mean()>250
    assert np.asarray(Image.open(directory/'00007.png')).mean()<5
    square=segmentation.prepare_masks(clip,'1:1','fit')
    assert square['reused_inference'] and session.run.call_count==12
    assert (square['width'],square['height'])==(320,320)
    clip.source_start=.2;clip.duration=.2
    trimmed=segmentation.prepare_masks(clip,'1:1','fit')
    assert np.asarray(Image.open(tmp_path/f"matte_{trimmed['key']}"/'00000.png')).mean()<5
    clip.source_start=.1
    cancel=threading.Event()
    with pytest.raises(ProcessingCancelled):
        segmentation.prepare_masks(clip,'1:1','fit',progress=lambda _:cancel.set(),cancel=cancel)
    assert not list(tmp_path.glob('matte_work_*'))


def test_auto_reel_changed_source_refreshes_transcript_without_rebuilding_timeline(tmp_path,monkeypatch):
    from app.services import auto_edit,media
    source=tmp_path/'speaker.mp4';source.write_bytes(b'original')
    monkeypatch.setattr(media,'uploaded_path',lambda _:source)
    monkeypatch.setattr(media,'probe_media',lambda _:{'duration':4,'has_audio':True})
    monkeypatch.setattr(auto_edit,'UPLOAD_DIR',tmp_path)
    monkeypatch.setattr(auto_edit,'extract_audio_from_media',lambda _,target,**kw:Path(target).write_bytes(b'audio'))
    transcribe=Mock(return_value=[segment('Fresh speech.',start=0,end=1)])
    monkeypatch.setattr(auto_edit,'transcribe_audio_file',transcribe)
    monkeypatch.setattr(auto_edit,'_enhance_plan',lambda plan,_:plan)
    clip=ClipConfig(id='stable',image_url=source.name,media_type='video',start_time=0,duration=3)
    current=EditingPlan(duration_seconds=3,source_filename=source.name,source_fingerprint=speech.source_fingerprint(source),clips=[clip],
                        transcript=[segment('Old speech.')],subtitles=[segment('Manual correction.',start=2,end=3)])
    reused=auto_edit.generate_auto_edit_reel(source.name,current_plan=current,auto_broll=False,list_sounds=False)
    assert transcribe.call_count==0 and reused.subtitles[0].text=='Manual correction.'
    source.write_bytes(b'changed audio')
    changed=auto_edit.generate_auto_edit_reel(source.name,current_plan=current,auto_broll=False,list_sounds=False)
    assert transcribe.call_count==1 and changed.clips[0].id=='stable' and changed.duration_seconds==3
    assert {s.text for s in changed.subtitles}=={'Fresh speech.','Manual correction.'}
    assert changed.source_fingerprint!=current.source_fingerprint
