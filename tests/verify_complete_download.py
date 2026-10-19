"""Combine actual local speech, subject masks, cached Pixabay video and MP4 download."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.editing_plan import EditingPlan,VisualInsert
from app.core.config import FFMPEG_PATH
from app.services.segmentation import prepare_masks,mask_duration
import subprocess
import numpy as np

if __name__=='__main__':
    client=TestClient(app)
    plan=EditingPlan.model_validate_json(Path('test_artifacts/reference-edit-plan.json').read_text(encoding='utf8'))
    asset=json.loads(Path('test_artifacts/pixabay-live.json').read_text(encoding='utf8'))
    plan.visual_inserts=[VisualInsert(id='verified-background',asset_id=str(asset['asset_id']),asset_url=asset['url'],
        media_type='video',start_time=1.8,duration=1.6,mode='background',source_page=asset['source_page'],source_clip_id=plan.clips[0].id)]
    prepare_masks(plan.clips[0],plan.aspect_ratio,plan.fit_mode,mask_duration(plan,plan.clips[0]))
    started=time.monotonic()
    response=client.post('/api/render',json={'plan':plan.model_dump(),'image_filenames':[plan.source_filename]})
    assert response.status_code==200,response.text
    identity=response.json()['job_id']
    assert client.get(f'/api/render/{identity}/download').status_code==404
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        status=client.get(f'/api/render/{identity}').json()
        if status['status'] in ('failed','completed'):
            assert status['status']=='completed',status
            break
        time.sleep(.2)
    else:raise AssertionError('Complete download exceeded 120 seconds')
    download=client.get(f'/api/render/{identity}/download')
    assert download.headers['content-type']=='video/mp4'
    assert f'rayflow_{identity}.mp4' in download.headers['content-disposition']
    path=Path('test_artifacts/complete-cinematic-download.mp4');path.write_bytes(download.content)
    decode=subprocess.run([FFMPEG_PATH,'-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True)
    assert decode.returncode==0,decode.stderr
    raw=subprocess.run([FFMPEG_PATH,'-v','error','-i',str(path),'-vf','scale=2:2','-pix_fmt','gray','-fps_mode','passthrough','-f','rawvideo','-'],capture_output=True,check=True).stdout
    assert len(raw)//4==120
    # Inspect the exported stereo channels directly: FFmpeg's mono downmix can
    # amplify correlated channels and report a peak absent from the actual file.
    audio=subprocess.run([FFMPEG_PATH,'-v','error','-i',str(path),'-vn','-ac','2','-ar','48000','-f','f32le','-'],capture_output=True,check=True).stdout
    pcm=np.frombuffer(audio,np.float32).reshape(-1,2)
    channel_rms=np.sqrt(np.mean(pcm**2,axis=0));channel_peaks=np.max(np.abs(pcm),axis=0)
    assert np.all(channel_rms>.01) and np.all(channel_peaks<1),(channel_rms,channel_peaks)
    subprocess.run([FFMPEG_PATH,'-v','error','-y','-ss','2.4','-i',str(path),'-frames:v','1','test_artifacts/complete-cinematic-frame.png'],check=True)
    record={'download':str(path),'bytes':len(download.content),'frames':len(raw)//4,'duration':4,'width':1080,'height':1920,
            'content_type':download.headers['content-type'],'disposition':download.headers['content-disposition'],
            'full_decode':True,'elapsed_seconds':round(time.monotonic()-started,2),
            'audio_channel_rms':channel_rms.tolist(),'audio_channel_peaks':channel_peaks.tolist()}
    Path('test_artifacts/complete-download-verification.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps(record))
