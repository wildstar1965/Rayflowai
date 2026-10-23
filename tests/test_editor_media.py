"""Exercise the reused worker against real media; requires installed Node dependencies."""
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.editor.context import workspace_id
from app.editor.store import store
from app.editor.runtime import RUNTIME, run_operation
from app.services.media import probe_media
from app.core.config import FFMPEG_PATH, FFPROBE_PATH


def test_codec_capabilities_match_required_cpu_exports():
    from app.editor.capabilities import codec_capabilities
    capabilities = codec_capabilities(FFMPEG_PATH)
    for codec in ('h264', 'hevc', 'prores'):
        assert capabilities[codec]['available'], capabilities[codec]['reason']
        assert capabilities[codec]['encoders']


@pytest.mark.parametrize('codec,container,depth,format_name', [
    ('h264', 'mp4', 8, 'h264'), ('hevc', 'mp4', 10, 'hevc'), ('prores', 'mov', 10, 'prores'),
])
def test_editor_ffmpeg_video_audio_and_private_output(tmp_path, monkeypatch, codec, container, depth, format_name):
    if not shutil.which('node'):
        pytest.skip('Node is not installed')
    dependency = subprocess.run(['node', '-e', "require.resolve('fluent-ffmpeg')"], cwd=RUNTIME, capture_output=True)
    if dependency.returncode:
        pytest.skip('Run npm install in backend/editor-runtime before the media check')
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    token = workspace_id.set('media-test-guest')
    try:
        buffer = io.BytesIO()
        Image.new('RGB', (320, 180), (20, 190, 50)).save(buffer, format='PNG')
        store.put_blob('media-test-guest', 'assets/green.png', buffer.getvalue())
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
            samples = (np.sin(2 * np.pi * 440 * np.arange(48000) / 48000) * 4000).astype('<i2')
            wav.writeframes(samples.tobytes())
        store.put_blob('media-test-guest', 'assets/tone.wav', audio.getvalue())
        project = {
            'mediaItems': [
                {'id': 'image', 'type': 'image', 'url': '/api/editor/assets/file/assets/green.png'},
                {'id': 'tone', 'type': 'audio', 'url': '/api/editor/assets/file/assets/tone.wav'}],
            'timelineTracks': [{'id': 'v1', 'type': 'video'}, {'id': 'a1', 'type': 'audio'}],
            'timelineClips': [
                {'id': 'c1', 'mediaId': 'image', 'trackId': 'v1', 'start': 0, 'end': 1, 'duration': 1, 'speed': 1},
                {'id': 'c2', 'mediaId': 'tone', 'trackId': 'a1', 'start': 0, 'end': 1, 'duration': 1, 'speed': 1}],
        }
        result = run_operation('export', {'project': project, 'settings': {
            'width': 320, 'height': 180, 'fps': 24, 'filename': 'verification.' + container,
            'videoCodec': codec, 'container': container, 'bitDepth': depth, 'gpuAcceleration': 'off'}},
            'media-verification', threading.Event(), lambda value: None)
        assert result['url'].startswith('/api/editor/assets/file/generated/')
        output = store.get_blob('media-test-guest', result['url'].removeprefix('/api/editor/assets/file/'))
        info = probe_media(output)
        assert info['width'] == 320 and info['height'] == 180
        assert abs(info['duration'] - 1) < 0.15
        assert info['has_video'] and info['has_audio']
        streams = json.loads(subprocess.run([FFPROBE_PATH, '-v', 'error', '-show_streams', '-of', 'json', str(output)],
                                            capture_output=True, check=True).stdout)['streams']
        video = next(stream for stream in streams if stream['codec_type'] == 'video')
        assert video['codec_name'] == format_name
        if depth == 10:
            assert '10' in video['pix_fmt']
        decoded = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-frames:v', '1',
                                  '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], capture_output=True, check=True)
        frame = np.frombuffer(decoded.stdout, dtype=np.uint8).reshape(180, 320, 3)
        red, green, blue = frame[90, 160]
        assert green > red + 70 and green > blue + 70
        decoded_audio = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-vn',
                                        '-f', 's16le', '-ac', '1', 'pipe:1'], capture_output=True, check=True)
        assert np.abs(np.frombuffer(decoded_audio.stdout, dtype='<i2').astype(np.int32)).mean() > 100
        assert store.get('assets', 'media-verification', 'media-test-guest')['url'] == result['url']
        assert not store.get('assets', 'media-verification', 'another-guest')
        assert not store.blob_path('media-test-guest', 'processing/media-verification').exists()
    finally:
        workspace_id.reset(token)


@pytest.mark.parametrize('easing', ['linear', 'ease-in', 'ease-out', 'ease-in-out'])
def test_export_volume_keyframes_follow_preview_timing(tmp_path, monkeypatch, easing):
    from app.editor.runtime import mix_timeline_audio
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    token = workspace_id.set('audio-keyframe-guest')
    try:
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
            wav.writeframes((np.sin(2 * np.pi * 440 * np.arange(48000 * 5) / 48000) * 8000).astype('<i2').tobytes())
        store.put_blob('audio-keyframe-guest', 'assets/tone.wav', audio.getvalue())
        output = tmp_path / 'automation.mp4'
        subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=24:d=4',
                        '-c:v', 'libx264', str(output)], check=True, capture_output=True)
        clip = {'id': 'tone', 'mediaId': 'tone', 'trackId': 'a1', 'start': 1, 'end': 3,
                'sourceIn': 1, 'sourceOut': 5, 'speed': 2, 'volume': 0,
                'keyframes': [{'property': 'volume', 'time': 0, 'value': .2, 'easing': 'linear'},
                              {'property': 'volume', 'time': 4, 'value': .8, 'easing': easing}]}
        project = {'mediaItems': [{'id': 'tone', 'type': 'audio', 'url': '/api/editor/assets/file/assets/tone.wav'}],
                   'timelineTracks': [{'id': 'a1', 'type': 'audio'}, {'id': 'muted', 'type': 'audio', 'isMuted': True}],
                   'timelineClips': [clip, {**clip, 'id': 'muted', 'trackId': 'muted'}]}
        mix_timeline_audio(output, project, 'keyframes', threading.Event())
        decoded = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-vn', '-ar', '48000', '-ac', '1',
                                  '-f', 'f32le', 'pipe:1'], capture_output=True, check=True).stdout
        samples = np.frombuffer(decoded, dtype='<f4')
        assert np.max(np.abs(samples[4800:40000])) < .001, 'Timeline delay must be silent.'
        for fraction in (.25, .5, .75):
            moment = 1 + 2 * fraction
            segment = samples[round((moment - .02) * 48000):round((moment + .02) * 48000)]
            measured = float(np.sqrt(np.mean(segment ** 2))) / (8000 / 32768 / np.sqrt(2))
            curve = fraction
            if easing == 'ease-in': curve = fraction ** 2
            if easing == 'ease-out': curve = fraction * (2 - fraction)
            if easing == 'ease-in-out': curve = 2 * fraction ** 2 if fraction < .5 else -1 + (4 - 2 * fraction) * fraction
            assert abs(measured - (.2 + .6 * curve)) < .035
    finally:
        workspace_id.reset(token)


@pytest.mark.parametrize('keyframes', [
    [{'property': 'volume', 'time': float('nan'), 'value': 1}],
    [{'property': 'volume', 'time': 0, 'value': '1;amovie=private-file'}],
    [{'property': 'volume', 'time': 0, 'value': 1, 'easing': 'custom-code'}],
    [{'property': 'volume', 'time': 0, 'value': 1}] * 2,
])
def test_export_rejects_invalid_audio_keyframes(keyframes):
    from app.editor.audio_automation import volume_filter
    with pytest.raises(ValueError):
        volume_filter({'keyframes': keyframes}, 1)


@pytest.mark.parametrize('is3d,intensity', [(True, 100), (True, 50), (False, 100)])
def test_custom_lut_changes_rendered_pixels(tmp_path, monkeypatch, is3d, intensity):
    monkeypatch.setenv('RAYFLOW_ENV', 'test')
    monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    token = workspace_id.set('lut-guest')
    try:
        buffer = io.BytesIO()
        Image.new('RGB', (160, 90), (64, 128, 192)).save(buffer, format='PNG')
        store.put_blob('lut-guest', 'assets/colors.png', buffer.getvalue())
        # Invert each channel: exercises 3D RGB ordering and 1D interpolation.
        values = [channel for blue in range(2) for green in range(2) for red in range(2)
                  for channel in (1-red, 1-green, 1-blue)] if is3d else [1, 1, 1, 0, 0, 0]
        lut = {'size': 2, 'is3d': is3d, 'domainMin': [0, 0, 0], 'domainMax': [1, 1, 1],
               'data': {str(i): value for i, value in enumerate(values)}}
        project = {'mediaItems': [{'id': 'image', 'type': 'image', 'url': '/api/editor/assets/file/assets/colors.png'}],
                   'timelineTracks': [{'id': 'v1', 'type': 'video'}],
                   'timelineClips': [{'id': 'c1', 'mediaId': 'image', 'trackId': 'v1', 'start': 0, 'end': .5,
                       'duration': .5, 'speed': 1, 'filters': {'lut': 'custom', 'lutIntensity': intensity, 'customLut': lut}}]}
        result = run_operation('export', {'project': project, 'settings': {'width': 160, 'height': 90, 'fps': 24,
            'filename': 'lut.mp4', 'gpuAcceleration': 'off'}}, 'lut-render', threading.Event(), lambda value: None)
        output = store.get_blob('lut-guest', result['url'].removeprefix('/api/editor/assets/file/'))
        decoded = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-frames:v', '1', '-pix_fmt', 'rgb24',
                                  '-f', 'rawvideo', 'pipe:1'], capture_output=True, check=True).stdout
        color = np.frombuffer(decoded, dtype=np.uint8).reshape(90, 160, 3)[45, 80].astype(float)
        original = np.array([64, 128, 192])
        expected = original * (1-intensity/100) + (255-original) * intensity/100
        assert np.max(np.abs(color-expected)) < 10, (color, expected)
    finally:
        workspace_id.reset(token)


@pytest.mark.parametrize('patch', [
    {'size': 100000}, {'data': [0]}, {'data': ['0;movie=private-file'] * 6},
    {'domainMin': [1, 0, 0]},
])
def test_custom_lut_rejects_malformed_data_before_writing(tmp_path, patch):
    lut = {'size': 2, 'is3d': False, 'domainMin': [0, 0, 0], 'domainMax': [1, 1, 1], 'data': [0, 0, 0, 1, 1, 1], **patch}
    target = tmp_path / 'invalid.cube'
    script = "const fs=require('fs'); const {writeCubeLut}=require('./cube-lut.cjs'); try { writeCubeLut(JSON.parse(fs.readFileSync(0,'utf8')),process.argv[1]); process.exitCode=2; } catch { process.exitCode=0; }"
    process = subprocess.run(['node', '-e', script, str(target)], input=json.dumps(lut), text=True,
                             capture_output=True, timeout=15, cwd=RUNTIME)
    assert process.returncode == 0
    assert not target.exists()
