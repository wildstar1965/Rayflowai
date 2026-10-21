"""Opt-in real-media Auto Reel comparison. Never replaces generated text or timings.

Run before on the baseline checkout, then after with the same source and model.
Artifacts are retained under test_artifacts/reel-quality.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import FFMPEG_PATH, UPLOAD_DIR, EXPORT_DIR
from app.services.auto_edit import generate_auto_edit_reel
from app.services.media import probe_media
from app.services.video_renderer import start_render_job, get_job_status

ART = ROOT / 'test_artifacts/reel-quality'


def ffmpeg(*args):
    return subprocess.check_output([FFMPEG_PATH, '-v', 'error', '-y', *map(str, args)])


def inspect(path, label):
    ART.mkdir(exist_ok=True, parents=True)
    info = probe_media(path)
    probe = os.getenv('FFPROBE_PATH') or shutil.which('ffprobe')
    if probe:
        metadata = json.loads(subprocess.check_output([probe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
        (ART / f'{label}-ffprobe.json').write_text(json.dumps(metadata, indent=2))
    decoded = subprocess.run([FFMPEG_PATH, '-hide_banner', '-xerror', '-i', str(path), '-vf', 'showinfo', '-f', 'null', '-'], capture_output=True, text=True)
    assert decoded.returncode == 0, decoded.stderr[-2000:]
    pts = [float(t) for t in re.findall(r'\bn:\s*\d+\s+pts:\s*\d+\s+pts_time:([\d.e+-]+)', decoded.stderr)]
    pcm = np.frombuffer(ffmpeg('-i', path, '-vn', '-ac', 1, '-ar', 16000, '-f', 'f32le', '-'), np.float32)
    raw = ffmpeg('-i', path, '-vf', 'fps=2,scale=180:320', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-')
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 320, 180, 3)
    all_frames=np.frombuffer(ffmpeg('-i',path,'-vf','scale=8:8','-pix_fmt','gray','-f','rawvideo','-'),np.uint8).reshape(-1,64)
    sheet = Image.new('RGB', (180*6, 344*((len(frames)+5)//6)), '#222222')
    draw = ImageDraw.Draw(sheet)
    for i, frame in enumerate(frames):
        x,y = i%6*180, i//6*344
        sheet.paste(Image.fromarray(frame),(x,y));draw.text((x+5,y+322), f'{i/2:.1f}s', fill='white')
    sheet.save(ART/f'{label}-contact.png')
    report = {**info, 'frames':len(pts), 'fps':round(1/float(np.median(np.diff(pts))),3),
              'video_codec':'H.264' if 'Video: h264' in decoded.stderr else 'other',
              'audio_codec':'AAC' if 'Audio: aac' in decoded.stderr else 'other',
              'uniform_30fps':bool(pts and np.allclose(np.diff(pts),1/30,atol=.0001)),
              'full_decode':True, 'ffprobe':bool(probe), 'audio_peak':float(np.abs(pcm).max()),
              'audio_rms':float(np.sqrt(np.mean(pcm**2))), 'near_black_frames':int(sum(f.mean()<2 for f in all_frames)),
              'audio_samples':len(pcm), 'audio_seconds':len(pcm)/16000}
    (ART/f'{label}-inspection.json').write_text(json.dumps(report,indent=2))
    return report


def render(plan, label):
    started=time.monotonic()
    job=start_render_job(plan,[plan.source_filename])
    while time.monotonic()-started<900:
        state=get_job_status(job)
        if state.status=='failed':raise RuntimeError(state.error)
        if state.status=='completed':break
        time.sleep(.25)
    else:raise TimeoutError('Render exceeded 15 minutes')
    path=ART/f'{label}.mp4'
    shutil.copyfile(EXPORT_DIR/f'rayflow_{job}.mp4',path)
    return inspect(path,label)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('label', choices=['before','after','reference'])
    parser.add_argument('--model',default='base')
    args=parser.parse_args()
    ART.mkdir(parents=True,exist_ok=True)
    if args.label=='reference':
        print(json.dumps(inspect(args.source,'reference'),indent=2));sys.exit(0)
    source=UPLOAD_DIR/'quality_speaker.mp4'
    if not source.exists() or source.read_bytes()!=args.source.read_bytes():
        shutil.copyfile(args.source,source)
    started=time.monotonic()
    def report(stage):print(f'{time.monotonic()-started:.1f}s {stage}',flush=True)
    plan=generate_auto_edit_reel(source.name,style_key='cinematic',whisper_model=args.model,
                                auto_broll=True,list_sounds=True,progress=report)
    (ART/f'{args.label}-plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf8')
    result=render(plan,args.label)
    result['total_seconds']=round(time.monotonic()-started,2)
    print(json.dumps(result),flush=True)
