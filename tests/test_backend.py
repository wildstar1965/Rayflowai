import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.editing_plan import EditingPlan, CommandRequest
from app.services.command_interpreter import interpret_command
from app.services.timeline_builder import build_timeline

def test_editing_plan_defaults():
    plan = EditingPlan()
    assert plan.duration_seconds == 15.0
    assert plan.aspect_ratio == "9:16"
    assert plan.style == "cinematic"
    assert plan.beat_sync is True
    assert plan.title.enabled is True

def test_command_interpreter_pacing_and_duration():
    cmd = "Make a 20-second cinematic travel reel with fast cuts and title: BENGAL ODYSSEY"
    req = CommandRequest(command=cmd)
    resp = interpret_command(req)

    assert resp.plan.duration_seconds == 20.0
    assert resp.plan.cut_pacing == "fast"
    assert resp.plan.title.text == "BENGAL ODYSSEY"
    assert "20.0s" in resp.explanation or "20s" in resp.explanation

def test_command_interpreter_aspect_ratio():
    cmd = "Export in vertical 9:16 format with slow zooms"
    req = CommandRequest(command=cmd)
    resp = interpret_command(req)

    assert resp.plan.aspect_ratio == "9:16"
    assert resp.plan.motion == "slow_zoom"

def test_timeline_builder_clips_generation():
    images = ["img1.jpg", "img2.jpg", "img3.jpg"]
    plan = EditingPlan(duration_seconds=12.0, cut_pacing="balanced")
    clips = build_timeline(images, plan, None)

    assert len(clips) >= 3
    # Check total duration roughly matches
    total_dur = sum(c.duration for c in clips)
    assert abs(total_dur - 12.0) < 1.0

if __name__ == "__main__":
    test_editing_plan_defaults()
    test_command_interpreter_pacing_and_duration()
    test_command_interpreter_aspect_ratio()
    test_timeline_builder_clips_generation()
    print("All unit tests passed successfully!")
