import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.editing_plan import EditingPlan, ClipConfig, AudioAnalysisResult, CommandRequest
from app.services.auto_edit import generate_auto_edit_reel
from app.services.timeline_builder import build_timeline
from app.services.command_interpreter import interpret_command
from app.services.video_renderer import _resolve_image_path
from app.core.config import UPLOAD_DIR

client = TestClient(app)


@pytest.fixture(autouse=True)
def workspace_session():
    # Media reads now require the same workspace session used for uploads.
    assert client.post('/api/session').status_code == 200


def upload_image(color='red'):
    output = io.BytesIO()
    Image.new('RGB', (320, 180), color).save(output, 'PNG')
    response = client.post('/api/media/images', files=[('files', ('audit.png', output.getvalue(), 'image/png'))])
    assert response.status_code == 200, response.text
    return response.json()['images'][0]


def test_auto_reel_retains_assets_ratio_and_resolvable_urls():
    assets = [upload_image(color) for color in ['red', 'green', 'blue']]
    response = client.post('/api/auto-edit', json={
        'media_filename': assets[0]['filename'], 'available_assets': assets,
        'aspect_ratio': '16:9', 'style_key': 'cinematic', 'include_captions': False,
    })
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan['aspect_ratio'] == '16:9'
    assert {c['image_url'] for c in plan['clips']} == {a['url'] for a in assets}
    assert sum(c['duration'] for c in plan['clips']) == pytest.approx(plan['duration_seconds'])
    assert all(client.get(c['image_url']).status_code == 200 for c in plan['clips'])
    assert len(plan['transitions']) == len(plan['clips']) - 1


def test_upload_rejects_corrupt_or_partially_unsupported_batches():
    assert client.post('/api/media/images', files=[('files', ('bad.png', b'invalid', 'image/png'))]).status_code == 400
    before = set(UPLOAD_DIR.iterdir())
    output = io.BytesIO()
    Image.new('RGB', (10, 10)).save(output, 'PNG')
    response = client.post('/api/media/images', files=[
        ('files', ('ok.png', output.getvalue(), 'image/png')),
        ('files', ('bad.txt', b'bad', 'text/plain')),
    ])
    assert response.status_code == 400
    assert set(UPLOAD_DIR.iterdir()) == before


def test_missing_media_is_not_silently_replaced():
    asset = upload_image()
    with pytest.raises(FileNotFoundError):
        _resolve_image_path('audit-does-not-exist.png', [asset['filename']])
    response = client.post('/api/auto-edit', json={'media_filename': 'audit-missing.mp4'})
    assert response.status_code == 404
    plan = EditingPlan(duration_seconds=2, clips=[ClipConfig(id='c', image_url='audit-missing.png', start_time=0, duration=2)])
    assert client.post('/api/render', json={'plan': plan.model_dump(), 'image_filenames': [asset['filename']]}).status_code == 400


def test_timeline_respects_disabled_beats_and_keeps_dense_assets():
    analysis = AudioAnalysisResult(duration=6, tempo=120, beat_count=3, beat_times=[0.5, 4.9, 5.4], strong_beats=[], sample_rate=22050)
    plan = EditingPlan(duration_seconds=6, beat_sync=False)
    clips = build_timeline(['a', 'b', 'c'], plan, analysis)
    assert [c.start_time for c in clips] == [0, 2, 4]
    plan = EditingPlan(duration_seconds=2)
    clips = build_timeline([str(i) for i in range(10)], plan, analysis)
    assert len({c.image_url for c in clips}) == 10
    assert all(c.duration >= 0.5 for c in clips)
    assert sum(c.duration for c in clips) == pytest.approx(plan.duration_seconds)


def test_disabled_sync_and_generic_reel_command_preserve_landscape():
    plan = EditingPlan(aspect_ratio='16:9', clips=[ClipConfig(id='c', image_url='a', start_time=0, duration=3)])
    result = interpret_command(CommandRequest(command='Disable beat sync in this reel', current_plan=plan))
    assert result.plan.beat_sync is False
    assert result.plan.aspect_ratio == '16:9'


def test_ollama_route_uses_clip_grammar_before_restricted_llm():
    plan = EditingPlan(clips=[ClipConfig(id='c', image_url='a', start_time=0, duration=3)])
    with patch('app.services.ollama_client.interpret_with_ollama', side_effect=AssertionError('LLM should not run')):
        response = client.post('/api/ollama/interpret', json={'command': 'Make the first photo last two seconds', 'plan': plan.model_dump()})
    assert response.status_code == 200, response.text
    assert response.json()['plan']['clips'][0]['duration'] == 2
