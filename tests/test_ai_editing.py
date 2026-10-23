import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.ai_editing import AIAction, AIEditingPlan
from app.schemas.editing_plan import ClipConfig, EditingPlan
from app.services.ai_editing import AIEditingError, apply_actions


def make_plan() -> EditingPlan:
    return EditingPlan(
        duration_seconds=8,
        clips=[
            ClipConfig(id="clip-a", image_url="a.mp4", start_time=0, duration=4,
                       source_duration=4, media_type="video", motion="static"),
            ClipConfig(id="clip-b", image_url="b.mp4", start_time=4, duration=4,
                       source_duration=4, media_type="video", motion="static"),
        ],
    )


def ai(*actions: AIAction) -> AIEditingPlan:
    return AIEditingPlan(explanation="Test plan", actions=list(actions))


def test_aspect_ratio_and_volume_use_real_clip():
    plan, changes = apply_actions(make_plan(), ai(
        AIAction(type="set_aspect_ratio", params={"aspect_ratio": "1:1"}),
        AIAction(type="set_clip_volume", params={"clip_id": "clip-a", "volume": 0.5}),
    ))
    assert plan.aspect_ratio == "1:1"
    assert plan.clips[0].volume == 0.5
    assert len(changes) == 2


def test_invalid_clip_id_is_rejected():
    with pytest.raises(AIEditingError, match="does not exist"):
        apply_actions(make_plan(), ai(AIAction(
            type="set_clip_volume", params={"clip_id": "missing", "volume": 1},
        )))


def test_split_preserves_source_and_changes_duration_explicitly():
    plan, _ = apply_actions(make_plan(), ai(AIAction(
        type="split_clip", params={"clip_id": "clip-a", "timestamp": 1.5},
    )))
    assert len(plan.clips) == 3
    assert plan.clips[0].duration == 1.5
    assert plan.clips[1].source_start == 1.5
    assert plan.duration_seconds == 8


def test_trim_requires_explicit_request_and_preserves_other_clip():
    with pytest.raises(AIEditingError, match="explicit"):
        apply_actions(make_plan(), ai(AIAction(
            type="trim_clip", params={"clip_id": "clip-a", "source_start": 1, "source_end": 3},
        )))
    plan, _ = apply_actions(make_plan(), ai(AIAction(
        type="trim_clip", params={"clip_id": "clip-a", "source_start": 1, "source_end": 3, "explicit": True},
    )))
    assert plan.clips[0].duration == 2
    assert plan.clips[1].duration == 4


def test_invalid_timestamp_is_rejected():
    with pytest.raises(AIEditingError, match="inside"):
        apply_actions(make_plan(), ai(AIAction(
            type="split_clip", params={"clip_id": "clip-a", "timestamp": 4},
        )))


def test_subtitles_validate_intervals_and_words():
    plan, _ = apply_actions(make_plan(), ai(AIAction(
        type="add_subtitles",
        params={"segments": [{
            "text": "hello world", "start_time": 0, "end_time": 2,
            "words": [{"word": "hello", "start": 0, "end": 1, "emphasis": True}],
        }]},
    )))
    assert plan.subtitles[0].words[0].emphasis is True
