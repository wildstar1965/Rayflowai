"""Actual FFmpeg/FFprobe regressions for source ranges, CFR export and A/V sync."""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import FFMPEG_PATH, FFPROBE_PATH, UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import EditingPlan, ClipConfig, RenderJobStatus, CommandRequest
from app.services import video_renderer as renderer
from app.services.media import probe_media, probe_streams, stream_duration
from app.services.frame_timing import frame_at
from app.services.command_interpreter import interpret_command

ARTIFACTS = Path(__file__).resolve().parents[1] / 'test_artifacts' / 'export_duration_fix'
client = TestClient(app)


def ffmpeg(*args):
    result = subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', *map(str, args)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    return result.stdout


@pytest.fixture(scope='module')
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp('timing_sources')
    sources = {}
    for name, rate, duration in [('25fps', '25', '2.28'), ('ntsc', '30000/1001', '1.5015'),
                                 ('60fps', '60', '0.716667'), ('vfr', '30', '2.4')]:
        path = root / f'{name}.mp4'
        filters = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,0.8,0.999)'"
        if name == 'vfr':
            filters += ",select='if(lt(t,1.2),not(mod(n,3)),1)'"
        ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size=160x90:rate={rate}:duration={duration}',
               '-f', 'lavfi', '-i', f"aevalsrc=if(between(t\\,0.8\\,1)\\,0.4*sin(2*PI*997*t)\\,0):s=48000:d={duration}",
               '-vf', filters, '-fps_mode', 'vfr', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', path)
        sources[name] = path
    long = root / 'long.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=30:d=121.233333', '-c:v', 'libx264', long)
    sources['long'] = long
    image = root / 'image.png'
    Image.new('RGB', (160, 90), 'blue').save(image)
    sources['image'] = image
    return sources


def upload(path):
    response = client.post('/api/media/images', files=[('files', (path.name, path.read_bytes()))])
    assert response.status_code == 200, response.text
    return response.json()['images'][0]


def create_plan(assets, plan=None):
    response = client.post('/api/projects/plan', json={
        'image_filenames': [a['filename'] for a in assets],
        'plan': (plan or EditingPlan(aspect_ratio='16:9', title={'enabled': False})).model_dump(),
    })
    assert response.status_code == 200, response.text
    return EditingPlan.model_validate(response.json())


def render(plan, name, audio=None):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    job = 'duration-' + uuid.uuid4().hex[:8]
    directory = ARTIFACTS / job
    directory.mkdir()
    renderer._JOBS[job] = RenderJobStatus(job_id=job, status='queued', progress=0, created_at=0)
    renderer._render_worker(job, plan, [], str(audio) if audio else None, directory)
    assert renderer._JOBS[job].status == 'completed', renderer._JOBS[job].error
    output = EXPORT_DIR / f'rayflow_{job}.mp4'
    data = probe_streams(output, count_frames=True)
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    audio_stream = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    expected = frame_at(plan.duration_seconds)
    assert int(video['nb_read_frames']) == expected
    assert stream_duration(video) == pytest.approx(expected / 30, abs=1e-6)
    assert abs(stream_duration(audio_stream) - expected / 30) < .022
    timestamps = json.loads(subprocess.check_output([
        FFPROBE_PATH, '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(output)]))
    pts = [float(f['best_effort_timestamp_time']) for f in timestamps['frames']]
    assert pts[0] == 0
    assert np.allclose(np.diff(pts), 1 / 30, atol=1e-6)
    raw = ffmpeg('-xerror', '-i', output, '-map', '0:v:0', '-vf', 'scale=32:18',
                 '-pix_fmt', 'rgb24', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-')
    assert len(raw) // (32 * 18 * 3) == expected
    record = {'output': str(output), 'timeline_seconds': plan.duration_seconds,
              'video_seconds': stream_duration(video), 'audio_seconds': stream_duration(audio_stream),
              'expected_frames': expected, 'ffprobe_frames': int(video['nb_read_frames']),
              'raw_decoded_frames': len(raw) // (32 * 18 * 3),
              'rounding_seconds': expected / 30 - plan.duration_seconds,
              'timestamps_uniform': True}
    (ARTIFACTS / f'{name}.json').write_text(json.dumps(record, indent=2))
    return output, np.frombuffer(raw, np.uint8).reshape(-1, 18, 32, 3)


def test_upload_initialization_reorder_and_explicit_trim(sources):
    assets = [upload(sources[name]) for name in ('long', 'ntsc', 'image', 'vfr')]
    plan = create_plan(assets)
    for item, clip in zip(assets, plan.clips):
        if item['media_type'] == 'video':
            assert clip.duration == item['duration'] == probe_media(UPLOAD_DIR / item['filename'])['duration']
            assert clip.source_duration == clip.duration
            assert clip.source_start == 0
        else:
            assert clip.duration == 2.5
    assert plan.clips[0].duration > 120
    original = {c.id: (c.duration, c.source_start) for c in plan.clips}
    edited = interpret_command(CommandRequest(command='Move the first clip to the end', current_plan=plan)).plan
    assert edited.clips[-1].id == plan.clips[0].id
    assert {c.id: (c.duration, c.source_start) for c in edited.clips} == original
    edited.clips[0].duration = .4137
    edited.clips[0].source_start = .237
    rebuilt = create_plan(assets, edited)
    assert rebuilt.clips[0].duration == .4137
    assert rebuilt.clips[0].source_start == .237
    assert [c.id for c in rebuilt.clips] == [c.id for c in edited.clips]
    assert create_plan(assets, rebuilt).model_dump() == rebuilt.model_dump()


def test_auto_edit_defaults_preserve_full_long_video(sources):
    asset = upload(sources['long'])
    response = client.post('/api/auto-edit', json={'media_filename': asset['filename'],
        'include_captions': False, 'auto_broll': False, 'list_sounds': False})
    assert response.status_code == 200, response.text
    plan = EditingPlan.model_validate(response.json())
    assert len(plan.clips) == 1
    assert plan.clips[0].source_start == 0
    assert plan.duration_seconds == asset['duration']
    plan.clips[0].source_start = .237
    plan.clips[0].duration = .4137
    plan.duration_seconds = .4137
    plan.source_filename = None  # A manual timeline has never run Auto Edit.
    response = client.post('/api/auto-edit', json={'media_filename': asset['filename'],
        'current_plan': plan.model_dump(), 'include_captions': False, 'auto_broll': False, 'list_sounds': False})
    assert response.status_code == 200, response.text
    assert response.json()['clips'][0]['source_start'] == .237
    assert response.json()['clips'][0]['duration'] == .4137


@pytest.mark.parametrize('name', ['25fps', 'vfr', 'long'])
def test_single_uploaded_video_full_range(sources, name):
    source = sources[name]
    asset = upload(source)
    plan = create_plan([asset])
    if name == 'vfr':
        frames = json.loads(subprocess.check_output([FFPROBE_PATH, '-v', 'error', '-select_streams', 'v:0',
            '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(source)]))['frames']
        deltas = np.diff([float(f['best_effort_timestamp_time']) for f in frames])
        assert len(set(np.round(deltas, 4))) > 1  # This fixture really is VFR.
    output, frames = render(plan, 'single-' + name)
    if name != 'long':
        assert np.abs(frames[-1].astype(float) - frames[-6]).mean() > 1  # No frozen tail.
    if name == '25fps':
        # Both the white video marker and tone start at source time 0.8s.
        audio = np.frombuffer(ffmpeg('-i', output, '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'), np.float32)
        onset = np.flatnonzero(np.abs(audio) > .05)[0] / 48000
        flash = np.flatnonzero(frames.mean(axis=(1, 2, 3)) > 220)[0] / 30
        assert abs(onset - flash) <= 1 / 30


def test_mixed_rates_transitions_overlays_and_trimmed_audio(sources):
    assets = [upload(sources[name]) for name in ('ntsc', '25fps', '60fps', 'vfr')]
    plan = create_plan(assets)
    # A deliberate non-frame-aligned source trim must survive A/V rendering.
    plan.clips[1].source_start = .237
    plan.clips[1].duration -= .237
    plan = create_plan(assets, plan)
    plan.title.enabled = True
    plan.title.text = 'Timing verification'
    from app.schemas.editing_plan import SubtitleSegment, VisualInsert
    plan.subtitles = [SubtitleSegment(id='caption', text='Synchronized', start_time=.2, end_time=.6)]
    plan.visual_inserts = [VisualInsert(id='overlay', asset_id='image', asset_url=str(sources['image']),
                                      start_time=.2, duration=.4)]
    output, frames = render(plan, 'mixed-transitions-overlays-trim')
    # The second clip's marker must retain its source-relative audio timing.
    target = plan.clips[1].start_time + .8 - .237
    audio = np.frombuffer(ffmpeg('-i', output, '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'), np.float32)
    a = int((target - .1) * 48000)
    onset = a / 48000 + np.flatnonzero(np.abs(audio[a:int((target+.1)*48000)]) > .05)[0] / 48000
    flashes = np.flatnonzero(frames.mean(axis=(1, 2, 3)) > 220) / 30
    flash = flashes[np.argmin(abs(flashes - target))]
    assert abs(onset - target) < 1 / 30
    assert abs(flash - onset) <= 1 / 30


def test_short_transition_chain_regression_and_strict_validation(sources):
    durations = [.51, .51, .1, .51, .066, .37]
    clips = []
    start = 0
    for i, duration in enumerate(durations):
        clips.append(ClipConfig(id=str(i), image_url=str(sources['image']), start_time=start,
            duration=duration, motion='static', transition='crossfade' if i in (0, 3, 5) else 'none'))
        start += duration
    plan = EditingPlan(duration_seconds=start, aspect_ratio='16:9', clips=clips, title={'enabled': False})
    output, _ = render(plan, 'short-transition-regression')
    assert frame_at(start) == 62  # Original renderer decoded only 51 frames.
    with pytest.raises(RuntimeError, match='frame count'):
        renderer._validate_rendered_video(output, 1920, 1080, True, expected_frames=63)
    with pytest.raises(RuntimeError, match='Expected 1080x1920'):
        renderer._validate_rendered_video(output, 1080, 1920, True, expected_frames=62)


def test_source_overrun_is_rejected_instead_of_frozen(sources):
    asset = upload(sources['25fps'])
    plan = create_plan([asset])
    plan.clips[0].duration += 1
    plan.duration_seconds += 1
    with pytest.raises(AssertionError, match='beyond its source duration'):
        render(plan, 'invalid-range')


def test_leading_audio_offset_and_longer_audio_tail_are_preserved(sources, tmp_path):
    source = tmp_path / 'delayed-audio.mp4'
    ffmpeg('-i', sources['25fps'], '-itsoffset', '0.2', '-i', sources['25fps'],
           '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', source)
    asset = upload(source)
    assert asset['duration'] > asset['video_duration'] + .15
    plan = create_plan([asset])
    output, frames = render(plan, 'audio-offset-and-tail')
    audio = np.frombuffer(ffmpeg('-i', output, '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'), np.float32)
    onset = np.flatnonzero(np.abs(audio) > .05)[0] / 48000
    flash = np.flatnonzero(frames.mean(axis=(1, 2, 3)) > 220)[0] / 30
    assert onset - flash == pytest.approx(.2, abs=1 / 30)
