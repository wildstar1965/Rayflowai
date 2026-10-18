import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import FFMPEG_PATH, UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import EditingPlan, ClipConfig, TransitionConfig, SubtitleSegment, WordTiming, VisualInsert
from app.services.video_renderer import build_motion_filter, start_render_job, get_job_status


def run(*args):
    result = subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', *map(str, args)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    return result.stdout


def render(plan, paths, audio=None):
    job = start_render_job(plan, paths, audio)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = get_job_status(job)
        if status.status in ('failed', 'completed'):
            assert status.status == 'completed', status.error
            return EXPORT_DIR / f'rayflow_{job}.mp4'
        time.sleep(0.2)
    pytest.fail('Render exceeded 120 seconds')


def test_zoom_crop_rounding_has_no_pixel_jumps(tmp_path):
    source = tmp_path / 'grid.png'
    img = Image.new('RGB', (320, 180), 'white')
    ImageDraw.Draw(img).rectangle((150, 80, 170, 100), fill='black')
    img.save(source)
    frames = 90
    filters = {
        'old': "scale=320:180,zoompan=z='1.05+0.1*on/89':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=90:s=320x180:fps=30",
        'fixed': build_motion_filter(320, 180, 30, frames, 'zoom_in'),
    }
    scores = {}
    for name, vf in filters.items():
        raw = run('-filter_threads', '1', '-i', source, '-vf', vf, '-frames:v', frames, '-pix_fmt', 'gray', '-f', 'rawvideo', '-')
        video = np.frombuffer(raw, dtype=np.uint8).reshape(frames, 180, 320)
        weights = 255 - video[:, 65:115, 130:190].astype(float)
        xs = (weights.sum(axis=1) * np.arange(60)).sum(axis=1) / weights.sum(axis=(1, 2))
        ys = (weights.sum(axis=2) * np.arange(50)).sum(axis=1) / weights.sum(axis=(1, 2))
        scores[name] = float(np.sqrt(np.mean(np.diff(xs) ** 2 + np.diff(ys) ** 2)))
    print('Motion centroid jitter (RMS px/frame):', scores)
    assert scores['fixed'] < 0.3
    assert scores['fixed'] < scores['old'] * 0.6


def test_mixed_landscape_export_keeps_boundaries_and_source_audio():
    prefix = 'audit_' + uuid.uuid4().hex[:8]
    image_paths = []
    for i, color in enumerate(['red', 'blue']):
        path = UPLOAD_DIR / f'{prefix}_{i}.png'
        img = Image.new('RGB', (640, 360), color)
        ImageDraw.Draw(img).rectangle((180, 100, 460, 260), outline='white', width=8)
        img.save(path)
        image_paths.append(str(path))
    source = UPLOAD_DIR / f'{prefix}_source.mp4'
    run('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25:duration=2',
        '-f', 'lavfi', '-i', 'sine=frequency=997:sample_rate=48000:duration=2',
        '-vf', 'setsar=4/3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', source)
    clips = [
        ClipConfig(id='a', image_url=image_paths[0], start_time=0, duration=1.2, motion='static', transition='crossfade'),
        ClipConfig(id='b', image_url=image_paths[1], start_time=1.2, duration=1.2, motion='pan_right'),
        ClipConfig(id='c', image_url=str(source), start_time=2.4, duration=1.6, media_type='video', source_start=0.4, motion='static'),
    ]
    plan = EditingPlan(duration_seconds=4, aspect_ratio='16:9', clips=clips, title={'enabled': False},
        transitions=[TransitionConfig(id='off', from_clip_id='a', to_clip_id='b', type='crossfade', duration=0.4, enabled=False),
                     TransitionConfig(id='on', from_clip_id='b', to_clip_id='c', type='dip_white', duration=0.3)],
        subtitles=[SubtitleSegment(id='sub', text='Stable export', start_time=0.2, end_time=0.8,
            words=[WordTiming(word='Stable', start=0.2, end=0.4), WordTiming(word='export', start=0.4, end=0.8)])],
        visual_inserts=[VisualInsert(id='ins', asset_id='a', asset_url=image_paths[0], start_time=1.5, duration=0.5, mode='pip')])
    output = render(plan, image_paths + [str(source)])
    probe = subprocess.run([FFMPEG_PATH, '-hide_banner', '-i', str(output)], capture_output=True, text=True).stderr
    assert '1920x1080' in probe and '30 fps' in probe and 'Audio: aac' in probe
    run('-xerror', '-i', output, '-f', 'null', '-')  # Decode every video and audio packet.
    raw = run('-i', output, '-vf', 'scale=160:90', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-')
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 90, 160, 3)
    assert len(frames) == 120
    # The disabled transition must remain a hard cut; no earlier blue frames.
    assert frames[34, 5, 5, 0] > 180 and frames[34, 5, 5, 2] < 70
    assert frames[37, 5, 5, 2] > 180
    # The final source video keeps moving instead of freezing for overlap compensation.
    assert np.abs(frames[-2].astype(float) - frames[-8]).mean() > 2
    audio = np.frombuffer(run('-i', output, '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'), dtype=np.float32)
    assert np.sqrt(np.mean(audio[:48000] ** 2)) < 0.001
    assert np.sqrt(np.mean(audio[int(2.6 * 48000):int(3.7 * 48000)] ** 2)) > 0.02
    record = {'path': str(output), 'duration': 4, 'width': 1920, 'height': 1080,
              'fps': 30, 'frames': len(frames), 'audio': 'AAC; source audio synchronized', 'full_decode': True}
    (EXPORT_DIR / 'audit_verified_export.json').write_text(json.dumps(record, indent=2), encoding='utf8')
    print(json.dumps(record))


def test_multiple_transitions_preserve_exact_frame_count():
    paths = []
    clips = []
    start = 0
    for index, (duration, color) in enumerate([(2.5, 'red'), (3, 'green'), (2.5, 'blue')]):
        path = UPLOAD_DIR / f'audit_boundary_{uuid.uuid4().hex}.png'
        Image.new('RGB', (320, 180), color).save(path)
        paths.append(str(path))
        clips.append(ClipConfig(id=str(index), image_url=str(path), start_time=start,
                                duration=duration, motion='static', transition='crossfade'))
        start += duration
    plan = EditingPlan(duration_seconds=8, aspect_ratio='16:9', clips=clips, title={'enabled': False})
    output = render(plan, paths)
    raw = run('-i', output, '-vf', 'scale=2:2', '-pix_fmt', 'gray', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-')
    assert len(raw) // 4 == 240
