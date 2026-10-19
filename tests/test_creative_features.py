import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.schemas.editing_plan import EditingPlan, ClipConfig, SubtitleSegment, WordTiming, VisualInsert, SoundCue, CommandRequest
from app.services import pixabay
from app.services.broll import extract_concepts, regenerate_broll
from app.services.list_sounds import generate_list_cues
from app.services.command_interpreter import interpret_command
from app.services.speech_transcription import transcribe_audio_file
from fastapi.testclient import TestClient
from app.main import app

def segment(text, start=0):
    words=[WordTiming(word=word,start=start+index*.3,end=start+index*.3+.25) for index,word in enumerate(text.split())]
    return SubtitleSegment(id='sub',text=text,start_time=start,end_time=start+len(words)*.3,words=words)

@pytest.mark.parametrize('text,labels',[
    ('First, discipline. Second, consistency. Third, patience.', ['discipline','consistency','patience']),
    ('1. Planning. 2. Execution. 3. Review.', ['Planning','Execution','Review']),
    ('You need a laptop, a microphone, and a camera.', ['a laptop','a microphone','a camera']),
    ('There are three important things: planning, execution, and review.', ['planning','execution','review']),
    ('My favorite foods are biryani, dosa, and chicken curry.', ['biryani','dosa','chicken curry']),
    ('A laptop, a microphone, and a camera.', ['A laptop','a microphone','a camera']),
    ('You need a laptop, a microphone and a camera.', ['a laptop','a microphone','a camera']),
    ('You need a laptop and a microphone and a camera.', ['a laptop','a microphone','a camera']),
    ('Seventh, planning. Eighth, execution. Ninth, review.', ['planning','execution','review']),
])
def test_lists_and_real_word_timing(text, labels):
    sub=segment(text)
    cues=generate_list_cues([sub])
    assert [c.label for c in cues]==labels
    assert all(any(c.start_time==w.start for w in sub.words) for c in cues)
    assert len({c.id for c in cues})==len(cues)

@pytest.mark.parametrize('text',[
    'I went home, because it rained, and I slept.',
    'First impressions matter. It was my second chance.',
    'Well, this is an ordinary sentence, without a list.',
    'Today we work. Tomorrow we rest.',
])
def test_non_lists_do_not_click(text):
    assert not generate_list_cues([segment(text)])

def test_no_fabricated_item_timestamps():
    assert not generate_list_cues([SubtitleSegment(id='s',text='You need a laptop, a microphone, and a camera.',start_time=0,end_time=5)])


def test_spoken_list_crosses_transcription_segment_boundary():
    first=segment('You need a laptop,',0)
    second=segment('a microphone and a camera.',1.2)
    second.id='sub-2'
    cues=generate_list_cues([first,second])
    assert [cue.label for cue in cues]==['a laptop','a microphone','a camera']
    assert [cue.start_time for cue in cues]==pytest.approx([.9,1.5,2.4])

@pytest.fixture
def provider(monkeypatch,tmp_path):
    monkeypatch.setattr(pixabay,'CACHE',tmp_path)
    monkeypatch.setattr(pixabay,'UPLOAD_DIR',tmp_path)
    monkeypatch.setattr(pixabay,'_blocked_until',0)
    pixabay._requests.clear()
    monkeypatch.setenv('PIXABAY_API_KEY','test-only-token')
    return tmp_path

def image_hit(identity=42):
    return {'id':identity,'tags':'mountains, nature, snow','pageURL':f'https://pixabay.com/photos/id-{identity}/',
            'user':'Contributor','webformatURL':'https://cdn.pixabay.com/test.jpg','largeImageURL':'https://cdn.pixabay.com/test.jpg',
            'imageWidth':1920,'imageHeight':1080}

def response(data,status=200,headers=None):
    return Mock(status_code=status,headers=headers or {},json=lambda:data)

def test_provider_cache_ranking_and_secret_safety(provider,monkeypatch):
    get=Mock(return_value=response({'hits':[image_hit()]}));monkeypatch.setattr(requests,'get',get)
    first=pixabay.search('mountains','image');second=pixabay.search('mountains','image')
    assert first==second and get.call_count==1
    assert first[0]['relevance']==1
    assert '_download_url' not in first[0]
    assert 'test-only-token' not in ''.join(path.read_text() for path in provider.glob('*.json'))
    cache=next(provider.glob('search_*.json'));data=json.loads(cache.read_text());data['created']-=86401;cache.write_text(json.dumps(data))
    pixabay.search('mountains','image');assert get.call_count==2

def test_video_result_parser(provider,monkeypatch):
    hit={'id':9,'tags':'mountains','user':'Film','pageURL':'https://pixabay.com/videos/id-9/','duration':12,
         'videos':{'large':{'url':'https://cdn.pixabay.com/video/9.mp4','thumbnail':'https://cdn.pixabay.com/video/9.jpg','width':1920,'height':1080,'size':1000}}}
    monkeypatch.setattr(requests,'get',Mock(return_value=response({'hits':[hit]})))
    item=pixabay.search('mountains','video')[0]
    assert item['media_type']=='video' and item['duration']==12 and item['preview_url'].endswith('.jpg')

@pytest.mark.parametrize('code',[400,401,403,429,500])
def test_provider_http_failures_are_helpful_and_redacted(provider,monkeypatch,code):
    monkeypatch.setattr(requests,'get',Mock(return_value=response({},code)))
    with pytest.raises(pixabay.MediaProviderError) as failure: pixabay.search('mountain')
    assert 'test-only-token' not in str(failure.value)
    if code==429:
        assert pixabay._blocked_until>time.time()

def test_missing_key_and_network_failure(provider,monkeypatch):
    monkeypatch.delenv('PIXABAY_API_KEY')
    with pytest.raises(pixabay.MediaProviderError,match='PIXABAY_API_KEY'):pixabay.search('mountain')
    monkeypatch.setenv('PIXABAY_API_KEY','test-only-token')
    monkeypatch.setattr(requests,'get',Mock(side_effect=requests.ConnectionError('secret-test-only-token')))
    with pytest.raises(pixabay.MediaProviderError) as failure:pixabay.search('mountain')
    assert 'test-only-token' not in str(failure.value)

def test_download_only_selected_asset_and_safe_storage(provider,monkeypatch):
    monkeypatch.setattr(requests,'get',Mock(return_value=response({'hits':[image_hit()]})))
    pixabay.search('mountains')
    raw=io.BytesIO();Image.new('RGB',(80,40),'red').save(raw,'JPEG')
    download=response({},headers={'Content-Type':'image/jpeg'});download.iter_content=lambda _:iter([raw.getvalue()])
    get=Mock(return_value=download);monkeypatch.setattr(requests,'get',get)
    result=pixabay.download(42,'image')
    assert result['url']=='/api/uploads/pixabay_image_42.jpg'
    assert Image.open(provider/'pixabay_image_42.jpg').size==(80,40)
    assert pixabay.download(42,'image')==result and get.call_count==1
    assert not list(provider.glob('*.part'))
    with pytest.raises(pixabay.MediaProviderError):pixabay.download(43,'image')
    with pytest.raises(pixabay.MediaProviderError):pixabay._safe_url('https://pixabay.com.evil.invalid/a')
    with pytest.raises(pixabay.MediaProviderError):pixabay._safe_url('http://127.0.0.1/private')

def test_concepts_prioritize_concrete_specific_entities():
    concepts=extract_concepts([segment('Chicken biryani near mountains and an FPGA.')],use_ai=False)
    phrases=[c['phrase'] for c in concepts]
    assert 'chicken biryani' in phrases and 'chicken' not in phrases
    assert 'fpga' in phrases and 'mountains' in phrases
    assert not extract_concepts([segment('Consistency and discipline bring success.')],use_ai=False)

def test_regeneration_keeps_manual_and_suppressed_edits(monkeypatch):
    plan=EditingPlan(duration_seconds=20,source_filename='source.mp4',subtitles=[segment('The mountains are beautiful.',4)],
        visual_inserts=[VisualInsert(id='manual',asset_id='m',asset_url='local.png',start_time=0,duration=1,origin='manual')])
    calls=[]
    monkeypatch.setattr(pixabay,'search',lambda *args:[{'id':42,'score':10,'relevance':1,'media_type':'image'}])
    def download(*args):
        calls.append(args);return {'id':42,'url':'/api/uploads/pic.jpg','media_type':'image','source_page':'https://pixabay.com/photos/id-42/','contributor':'Person'}
    monkeypatch.setattr(pixabay,'download',download)
    first=regenerate_broll(plan,use_ai=False)
    assert first.visual_inserts[0]==plan.visual_inserts[0]
    assert len(first.visual_inserts)==2
    second=regenerate_broll(first,use_ai=False);assert len(calls)==1
    generated=second.visual_inserts[-1]
    second.suppressed_auto_inserts=[generated.id];second.visual_inserts=second.visual_inserts[:1]
    assert len(regenerate_broll(second,use_ai=False).visual_inserts)==1

def test_typed_ordinals_do_not_delete_video_or_unrelated_media():
    plan=EditingPlan(duration_seconds=6,clips=[ClipConfig(id='speaker',image_url='v.mp4',media_type='video',start_time=0,duration=2),
        ClipConfig(id='photo',image_url='p.jpg',start_time=2,duration=2),ClipConfig(id='last',image_url='q.jpg',start_time=4,duration=2)],
        sound_cues=[SoundCue(id='s',label='item',start_time=2.4,source_clip_id='photo')])
    result=interpret_command(CommandRequest(command='Remove the first photo',current_plan=plan),allow_llm=False)
    assert [c.id for c in result.plan.clips]==['speaker','last']
    assert not result.plan.sound_cues
    missing=interpret_command(CommandRequest(command='Remove the eighth photo',current_plan=plan),allow_llm=False)
    assert not missing.applied_changes and missing.plan==plan
    moved=interpret_command(CommandRequest(command='Move the first photo to the beginning',current_plan=plan),allow_llm=False)
    assert moved.plan.sound_cues[0].start_time==pytest.approx(.4)

def test_broll_removal_and_individual_sound_mute():
    plan=EditingPlan(visual_inserts=[VisualInsert(id='i',asset_id='a',asset_url='a.jpg',start_time=0,duration=2)],
                     sound_cues=[SoundCue(id='1',label='one',start_time=1),SoundCue(id='2',label='two',start_time=2)])
    removed=interpret_command(CommandRequest(command='Remove the first B-roll clip',current_plan=plan),allow_llm=False)
    assert not removed.plan.visual_inserts and removed.plan.suppressed_auto_inserts==['i']
    muted=interpret_command(CommandRequest(command='Mute the click sound on the second item',current_plan=plan),allow_llm=False)
    assert muted.plan.sound_cues[1].muted and not muted.plan.sound_cues[0].muted

def test_transcript_cache_uses_audio_content_not_temp_filename(tmp_path,monkeypatch):
    import app.services.speech_transcription as transcription
    monkeypatch.setattr(transcription,'CACHE_DIR',tmp_path)
    work=Mock(return_value=[segment('Actual speech')]);monkeypatch.setattr(transcription,'_transcribe_uncached',work)
    a=tmp_path/'a.wav';b=tmp_path/'b.wav';a.write_bytes(b'audio');b.write_bytes(b'audio')
    assert transcribe_audio_file(str(a),'tiny')==transcribe_audio_file(str(b),'tiny')
    assert work.call_count==1
    b.write_bytes(b'changed');transcribe_audio_file(str(b),'tiny');assert work.call_count==2

def test_unfinished_export_not_public_and_invalid_cues_rejected():
    client=TestClient(app)
    assert client.get('/api/exports/rayflow_unknown.mp4').status_code==404
    assert client.get('/api/sounds/soft.wav').headers['content-type']=='audio/wav'
    with pytest.raises(ValueError):SoundCue(id='x',label='x',start_time=float('nan'))

def test_matte_cache_key_survives_json_round_trip(tmp_path,monkeypatch):
    from app.services import segmentation
    source=tmp_path/'source.mp4';source.write_bytes(b'source')
    monkeypatch.setattr(segmentation,'uploaded_path',lambda _:source)
    clip=ClipConfig(id='c',image_url='source.mp4',media_type='video',start_time=0,duration=4)
    copy=ClipConfig.model_validate_json(clip.model_dump_json())
    assert segmentation.mask_key(clip,'9:16','fill',3.98)==segmentation.mask_key(copy,'9:16','fill',3.98)


def test_replacement_preserves_identity_layout_and_resets_source_clock(monkeypatch):
    original=VisualInsert(id='stable',asset_id='old',asset_url='old.mp4',media_type='video',
        start_time=2,duration=3,source_start=8,mode='pip',source_clip_id='speaker')
    plan=EditingPlan(duration_seconds=8,visual_inserts=[original])
    monkeypatch.setattr(pixabay,'download',lambda *_:{'url':'/api/uploads/new.mp4','source_page':'https://pixabay.com/videos/id-42/',
        'contributor':'Author','tags':'mountain','duration':1.5})
    response=TestClient(app).post('/api/broll/select',json={'plan':plan.model_dump(),'asset_id':42,'kind':'video','replace_id':'stable'})
    assert response.status_code==200,response.text
    updated=EditingPlan.model_validate(response.json()).visual_inserts[0]
    assert (updated.id,updated.start_time,updated.mode,updated.source_clip_id)==('stable',2,'pip','speaker')
    assert updated.source_start==0 and updated.duration==1.5 and updated.origin=='manual'
    assert original.source_start==8


def test_contextual_command_respects_media_type_and_source_attachment(monkeypatch):
    plan=EditingPlan(duration_seconds=8,clips=[ClipConfig(id='speaker',image_url='source.mp4',media_type='video',start_time=0,duration=8)],
        subtitles=[segment('We are talking about travel.',2)],visual_inserts=[
            VisualInsert(id='photo',asset_id='p',asset_url='p.jpg',label='Mountain',start_time=0,duration=1),
            VisualInsert(id='video',asset_id='v',asset_url='v.mp4',media_type='video',label='Mountain',start_time=0,duration=1)])
    search=Mock(side_effect=AssertionError('An existing matching video should be reused'))
    monkeypatch.setattr(pixabay,'search',search)
    result=interpret_command(CommandRequest(command='Put the mountain video when I start talking about travel.',current_plan=plan),allow_llm=False)
    assert result.applied_changes
    photo,video=result.plan.visual_inserts
    assert photo.start_time==0
    assert video.start_time==pytest.approx(3.2) and video.source_clip_id=='speaker'
    assert video.origin=='manual' and not search.called


def test_cancelled_render_is_stopped_and_never_downloadable(tmp_path,monkeypatch):
    from app.services import video_renderer
    from app.api import routes
    from app.schemas.editing_plan import RenderJobStatus
    identity='abcdef12'
    job=RenderJobStatus(job_id=identity,status='processing',progress=50,created_at=time.time())
    monkeypatch.setattr(video_renderer,'_JOBS',{identity:job})
    monkeypatch.setattr(routes,'EXPORT_DIR',tmp_path)
    (tmp_path/f'rayflow_{identity}.mp4').write_bytes(b'incomplete')
    client=TestClient(app)
    assert client.get(f'/api/render/{identity}/download').status_code==404
    assert client.post(f'/api/render/{identity}/cancel').status_code==200
    process=Mock();monkeypatch.setattr(video_renderer.subprocess,'Popen',Mock(return_value=process))
    with pytest.raises(RuntimeError,match='cancelled'):
        video_renderer._run_render(['unused'],identity)
    process.kill.assert_called_once()
    process.communicate.assert_called_once()
    assert job.status=='cancelled'
    assert client.get(f'/api/render/{identity}/download').status_code==404
    assert client.get(f'/api/exports/rayflow_{identity}.mp4').status_code==404
    assert client.post(f'/api/render/{identity}/cancel').status_code==409


def test_concurrent_alpha_requests_return_complete_frames(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.api import creative_routes
    monkeypatch.setattr(creative_routes,'CACHE_DIR',tmp_path)
    key='a'*64
    directory=tmp_path/f'matte_{key}';directory.mkdir()
    (directory/'ready.json').write_text('{}',encoding='utf8')
    Image.new('L',(32,48),128).save(directory/'00000.png')
    def read_frame(_):
        response=TestClient(app).get(f'/api/cinematic/masks/{key}/0.png?alpha=true')
        assert response.status_code==200
        with Image.open(io.BytesIO(response.content)) as frame:
            assert frame.mode=='RGBA' and frame.getpixel((5,5))[3]==128
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(read_frame,range(8)))
    assert not list(directory.glob('*.part'))


def test_cinematic_titles_preserve_line_breaks_and_long_heading_tail(tmp_path,monkeypatch):
    from app.services import cinematic
    monkeypatch.setattr(cinematic,'CACHE_DIR',tmp_path)
    def pixels(text):
        with Image.open(cinematic.title_image(text,'#E7C48C',1080,1920)) as raster:
            return raster.copy()
    single=pixels('YOUR STORY')
    two=pixels('YOUR\nSTORY')
    assert two.getbbox()[3]>single.getbbox()[3]+100
    prefix='A meaningful opening with deliberate words across several lines and a final '
    assert pixels(prefix+'REMINDER').tobytes()!=pixels(prefix+'PROMISE').tobytes()
    left,top,right,bottom=pixels(prefix+'REMINDER').getbbox()
    assert left>=50 and right<=1030 and top>=170 and bottom<1100


def test_concurrent_title_requests_share_a_complete_cached_raster(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.services import cinematic
    monkeypatch.setattr(cinematic,'CACHE_DIR',tmp_path)
    def read_title(_):
        path=cinematic.title_image('YOUR STORY','#F2E9D8',1080,1920)
        with Image.open(path) as raster:
            raster.load()
            assert raster.getbbox() is not None
        return path
    with ThreadPoolExecutor(max_workers=4) as workers:
        paths=list(workers.map(read_title,range(8)))
    assert len(set(paths))==1 and len(list(tmp_path.glob('*.png')))==1


def test_missing_subject_model_returns_setup_guidance(tmp_path,monkeypatch):
    from app.services import segmentation
    monkeypatch.setattr(segmentation,'model_path',lambda:tmp_path/'missing.onnx')
    assert not segmentation.availability()['available']
    clip=ClipConfig(id='speaker',image_url='source.mp4',media_type='video',start_time=0,duration=4)
    with pytest.raises(ValueError,match='setup_local_assets.py --video-matting'):
        segmentation.prepare_masks(clip,'9:16','fill')
