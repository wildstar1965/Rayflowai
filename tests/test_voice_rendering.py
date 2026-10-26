"""Rotated and moved pictures must survive both actual MP4 export paths."""
import io
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import FFMPEG_PATH


@pytest.mark.parametrize('workspace', ['studio', 'editor'])
def test_rotated_shifted_export_pixels(tmp_path, monkeypatch, workspace):
    image = Image.new('RGB', (128, 128), 'blue')
    ImageDraw.Draw(image).rectangle((0, 0, 127, 63), fill='red')
    source = tmp_path / 'two-colors.png'
    image.save(source)
    if workspace == 'studio':
        from app.schemas.editing_plan import EditingPlan
        from app.services import video_renderer as renderer
        monkeypatch.setattr(renderer, 'EXPORT_DIR', tmp_path)
        plan = EditingPlan(duration_seconds=.5, aspect_ratio='1:1', color_strength=0, title={'enabled': False},
                           clips=[dict(id='a', image_url=str(source), start_time=0, duration=.5, motion='static', rotation=90, offset_x=.25)])
        job = renderer.start_render_job(plan, [str(source)])
        deadline = time.monotonic() + 60
        while renderer.get_job_status(job).status not in ('completed', 'failed') and time.monotonic() < deadline:
            time.sleep(.1)
        status = renderer.get_job_status(job)
        assert status.status == 'completed', status.error
        output = tmp_path / f'rayflow_{job}.mp4'
    else:
        from app.editor.context import workspace_id
        from app.editor.runtime import run_operation
        from app.editor.store import store
        monkeypatch.setenv('RAYFLOW_STORAGE_DIR', str(tmp_path))
        monkeypatch.setenv('RAYFLOW_ENV', 'test')
        monkeypatch.delenv('SUPABASE_URL', raising=False)
        monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
        identity = 'rotation-export-test'
        token = workspace_id.set(identity)
        try:
            store.put_blob(identity, 'assets/two-colors.png', source.read_bytes())
            project = {'mediaItems': [{'id': 'm', 'type': 'image', 'url': '/api/editor/assets/file/assets/two-colors.png'}],
                       'timelineTracks': [{'id': 'v', 'type': 'video'}],
                       'timelineClips': [{'id': 'a', 'mediaId': 'm', 'trackId': 'v', 'start': 0, 'end': .5, 'duration': .5, 'speed': 1,
                                          'transform': {'scale': 1, 'opacity': 1, 'rotation': 90, 'position': {'x': 75, 'y': 50}}}]}
            result = run_operation('export', {'project': project, 'settings': {'width': 128, 'height': 128, 'fps': 24,
                                   'filename': 'rotation.mp4', 'gpuAcceleration': 'off'}}, 'rotation-test', threading.Event(), lambda _: None)
            output = store.get_blob(identity, result['url'].removeprefix('/api/editor/assets/file/'))
        finally:
            workspace_id.reset(token)
    frame = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(output), '-frames:v', '1', '-vf', 'scale=128:128',
                            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    pixels = np.frombuffer(frame, np.uint8).reshape(128, 128, 3)
    assert max(pixels[64, 10]) < 20  # newly exposed border after moving right
    assert pixels[64, 64, 2] > 180 and pixels[64, 64, 0] < 30  # blue on the left after clockwise rotation
    assert pixels[64, 115, 0] > 180 and pixels[64, 115, 2] < 30  # red on the right
