import sys
import os
import time
import subprocess
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import UPLOAD_DIR, EXPORT_DIR, FFMPEG_PATH
from app.schemas.editing_plan import EditingPlan, ClipConfig, TransitionConfig, GlobalTransitionConfig, CommandRequest
from app.services.video_renderer import start_render_job, get_job_status
from app.services.command_interpreter import interpret_command

def run_tests():
    print("=== RayFlow AI Advanced Workflow Test ===")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Create 4 test photographs
    img_names = []
    colors = [(220, 60, 60), (60, 200, 80), (60, 100, 230), (230, 180, 40)]
    for i, c in enumerate(colors):
        fn = f"e2e_photo_{i}.jpg"
        im = Image.new("RGB", (1200, 900), c)
        im.save(UPLOAD_DIR / fn)
        img_names.append(fn)
    print(f"1. Prepared 4 test photos: {img_names}")

    # 2. Test Natural Language Directives
    print("\n2. Testing Natural Language Editing Directives...")
    base_plan = EditingPlan(
        duration_seconds=8.0,
        aspect_ratio="9:16",
        fit_mode="fill",
        clips=[
            ClipConfig(id=f"clip-{i+1}", image_url=img_names[i], start_time=i * 2.0, duration=2.0)
            for i in range(4)
        ]
    )

    directives = [
        ("Change the video to landscape.", "16:9"),
        ("Apply a crossfade between photos one and two.", "crossfade"),
        ("Replace the transition between photos two and three with a dip to black.", "dip_black"),
        ("Add a fade-in at the beginning of the entire reel.", "fade_in"),
        ("Fade out the video at the end.", "fade_out"),
        ("Make the first photo last three seconds.", 3.0),
        ("Extend the third photo by two seconds.", 4.0),
        ("Move the last photo to the beginning.", "clip-4")
    ]

    p = base_plan
    for cmd, expected in directives:
        res = interpret_command(CommandRequest(command=cmd, current_plan=p))
        assert len(res.applied_changes) > 0, f"Directive failed: {cmd}"
        p = res.plan
        print(f"   [OK] Directive '{cmd}' -> {res.applied_changes[0]}")

    print("   All natural-language commands resolved and applied to project state.")

    # 3. Test Aspect Ratios & Real FFmpeg Exports
    print("\n3. Testing Real FFmpeg Exports across Aspect Ratios and Transitions...")
    test_cases = [
        ("9:16", 1080, 1920, "fill"),
        ("16:9", 1920, 1080, "fit"),
        ("1:1", 1080, 1080, "fill")
    ]

    for ratio, exp_w, exp_h, fit_mode in test_cases:
        print(f"\n   Testing Export {ratio} ({exp_w}x{exp_h}, {fit_mode})...")
        export_plan = EditingPlan(
            duration_seconds=4.5,
            aspect_ratio=ratio,
            fit_mode=fit_mode,
            clips=[
                ClipConfig(id="c1", image_url=img_names[0], start_time=0.0, duration=1.5, motion="zoom_in"),
                ClipConfig(id="c2", image_url=img_names[1], start_time=1.5, duration=1.5, motion="zoom_out"),
                ClipConfig(id="c3", image_url=img_names[2], start_time=3.0, duration=1.5, motion="zoom_in"),
            ],
            transitions=[
                TransitionConfig(id="t1", from_clip_id="c1", to_clip_id="c2", type="crossfade", duration=0.4, enabled=True),
                TransitionConfig(id="t2", from_clip_id="c2", to_clip_id="c3", type="dip_black", duration=0.4, enabled=True),
            ],
            head_transition=GlobalTransitionConfig(enabled=True, type="fade_in", duration=0.3),
            tail_transition=GlobalTransitionConfig(enabled=True, type="fade_out", duration=0.3)
        )

        job_id = start_render_job(export_plan, img_names[:3], None)
        success = False
        for _ in range(120):
            st = get_job_status(job_id)
            if st and st.status in ("completed", "failed"):
                if st.status == "completed":
                    success = True
                    print(f"   [OK] Render completed: {st.output_url}")
                    # Probe video
                    mp4_path = EXPORT_DIR / f"rayflow_{job_id}.mp4"
                    assert mp4_path.exists() and mp4_path.stat().st_size > 1000, "File empty"
                    probe = subprocess.run([FFMPEG_PATH, "-i", str(mp4_path)], capture_output=True, text=True)
                    text = probe.stderr
                    assert f"{exp_w}x{exp_h}" in text, f"Expected {exp_w}x{exp_h} in probe output"
                    print(f"   [OK] Validated dimensions: {exp_w}x{exp_h} confirmed via FFmpeg probe")
                else:
                    raise RuntimeError(f"Render failed: {st.error}")
                break
            time.sleep(0.4)
        assert success, f"Render timed out for {ratio}"

    print("\n=== ALL ADVANCED WORKFLOW TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_tests()
