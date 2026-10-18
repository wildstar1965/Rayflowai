import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.editing_plan import EditingPlan, CommandRequest, ClipConfig, TransitionConfig
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

def test_command_interpreter_removes_eighth_photo():
    clips = [
        ClipConfig(
            id=f"clip-{i + 1}",
            image_url=f"img{i + 1}.jpg",
            start_time=float(i),
            duration=1.0,
        )
        for i in range(8)
    ]
    plan = EditingPlan(
        duration_seconds=8.0,
        clips=clips,
    )
    plan.transitions = [
        {
            "id": f"transition-{i + 1}",
            "from_clip_id": clips[i].id,
            "to_clip_id": clips[i + 1].id,
        }
        for i in range(7)
    ]

    response = interpret_command(CommandRequest(
        command="Remove the eighth photo",
        current_plan=plan,
    ))

    assert len(response.plan.clips) == 7
    assert all(clip.image_url != "img8.jpg" for clip in response.plan.clips)
    assert response.plan.duration_seconds == 7.0
    assert all(
        (transition.get("from_clip_id") if isinstance(transition, dict) else transition.from_clip_id) != "clip-8"
        and (transition.get("to_clip_id") if isinstance(transition, dict) else transition.to_clip_id) != "clip-8"
        for transition in response.plan.transitions
    )

def test_clip_reorder_forward_and_backward_preserves_transitions():
    clips = [
        ClipConfig(id=f"clip-{i+1}", image_url=f"img{i+1}.jpg", start_time=float(i * 2), duration=2.0)
        for i in range(4)
    ]
    plan = EditingPlan(duration_seconds=8.0, clips=clips)
    plan.transitions = [
        TransitionConfig(id="t1", from_clip_id="clip-1", to_clip_id="clip-2", type="crossfade", duration=0.5, enabled=True),
        TransitionConfig(id="t2", from_clip_id="clip-2", to_clip_id="clip-3", type="dip_black", duration=0.4, enabled=True),
        TransitionConfig(id="t3", from_clip_id="clip-3", to_clip_id="clip-4", type="fade_in", duration=0.5, enabled=True),
    ]

    # Test 1: Move first photo to end (Forward)
    res_fwd = interpret_command(CommandRequest(command="Move the first photo to the end.", current_plan=plan))
    new_clips_fwd = [c.id for c in res_fwd.plan.clips]
    assert new_clips_fwd == ["clip-2", "clip-3", "clip-4", "clip-1"], f"Unexpected clip order: {new_clips_fwd}"

    # Verify transitions after forward move: clip-2->clip-3 (t2) and clip-3->clip-4 (t3) must be preserved!
    fwd_trans = { (t.from_clip_id, t.to_clip_id): t for t in res_fwd.plan.transitions }
    assert ("clip-2", "clip-3") in fwd_trans
    assert fwd_trans[("clip-2", "clip-3")].type == "dip_black"
    assert fwd_trans[("clip-2", "clip-3")].duration == 0.4
    assert ("clip-3", "clip-4") in fwd_trans
    assert fwd_trans[("clip-3", "clip-4")].type == "fade_in"
    assert ("clip-1", "clip-2") not in fwd_trans, "Old transition between non-adjacent clips must be purged"

    # Test 2: Move last photo to beginning (Backward)
    res_bwd = interpret_command(CommandRequest(command="Move the last photo to the beginning.", current_plan=res_fwd.plan))
    new_clips_bwd = [c.id for c in res_bwd.plan.clips]
    assert new_clips_bwd == ["clip-1", "clip-2", "clip-3", "clip-4"], f"Unexpected clip order: {new_clips_bwd}"

    # Verify transitions after backward move
    bwd_trans = { (t.from_clip_id, t.to_clip_id): t for t in res_bwd.plan.transitions }
    assert ("clip-2", "clip-3") in bwd_trans
    assert bwd_trans[("clip-2", "clip-3")].type == "dip_black"
    assert ("clip-3", "clip-4") in bwd_trans
    assert bwd_trans[("clip-3", "clip-4")].type == "fade_in"

if __name__ == "__main__":
    test_editing_plan_defaults()
    test_command_interpreter_pacing_and_duration()
    test_command_interpreter_aspect_ratio()
    test_timeline_builder_clips_generation()
    test_command_interpreter_removes_eighth_photo()
    test_clip_reorder_forward_and_backward_preserves_transitions()
    print("All unit tests passed successfully!")
