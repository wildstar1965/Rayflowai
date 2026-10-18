import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import EditingPlan, ClipConfig, TransitionConfig
from app.services.video_renderer import start_render_job, get_job_status


def _wait_for_render(job_id: str, timeout_seconds: int = 120):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = get_job_status(job_id)
        if status.status in ("completed", "failed"):
            return status
        time.sleep(1.0)
    raise AssertionError(f"Render job timed out: {job_id}")


def _probe_duration(file_path: Path) -> float:
    from app.core.config import FFMPEG_PATH
    result = subprocess.run(
        [FFMPEG_PATH, "-hide_banner", "-i", str(file_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    assert match, f"Could not read duration for {file_path}: {result.stderr[-500:]}"
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))

def test_full_render_pipeline():
    # 1. Create 3 test images in UPLOAD_DIR
    test_images = []
    colors = [(40, 60, 120), (120, 40, 80), (30, 100, 70)]
    for idx, col in enumerate(colors):
        img_path = UPLOAD_DIR / f"test_render_sample_{idx}.jpg"
        img = Image.new("RGB", (720, 1280), col)
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 670, 1230], outline=(255, 255, 255), width=6)
        draw.text((100, 600), f"RAYFLOW TEST #{idx+1}", fill=(255, 255, 255))
        img.save(img_path, "JPEG")
        test_images.append(str(img_path))

    # 2. Build editing plan
    plan = EditingPlan(
        duration_seconds=4.5,
        aspect_ratio="9:16",
        style="cinematic",
        title={"enabled": True, "text": "RAYFLOW CINEMA", "gradient": ["#67E8F9", "#3B82F6"]},
        clips=[
            ClipConfig(id="c1", image_url=test_images[0], start_time=0.0, duration=1.5, motion="zoom_in"),
            ClipConfig(id="c2", image_url=test_images[1], start_time=1.5, duration=1.5, motion="zoom_out"),
            ClipConfig(id="c3", image_url=test_images[2], start_time=3.0, duration=1.5, motion="zoom_in"),
        ]
    )

    # 3. Start render job
    job_id = start_render_job(plan, test_images, audio_filename=None)
    print(f"Render job started: {job_id}")

    # 4. Wait for job completion
    status = _wait_for_render(job_id)
    print(f"Status: {status.status}, Progress: {status.progress:.1f}%")

    final_status = get_job_status(job_id)
    assert final_status.status == "completed", f"Render failed: {final_status.error}"
    assert final_status.progress == 100.0

    output_file = EXPORT_DIR / f"rayflow_{job_id}.mp4"
    assert output_file.exists(), f"Output file does not exist: {output_file}"
    file_size = output_file.stat().st_size
    print(f"Successfully rendered video! File size: {file_size} bytes ({output_file})")
    assert file_size > 10000, "Rendered video file is too small!"


def test_long_render_with_transitions_and_audio():
    test_images = []
    colors = [(20, 80, 140), (140, 50, 80), (40, 120, 70)]
    for idx, col in enumerate(colors):
        img_path = UPLOAD_DIR / f"test_long_render_sample_{idx}.jpg"
        img = Image.new("RGB", (720, 1280), col)
        ImageDraw.Draw(img).text((100, 600), f"LONG TEST #{idx + 1}", fill=(255, 255, 255))
        img.save(img_path, "JPEG")
        test_images.append(str(img_path))

    audio_path = Path(__file__).resolve().parents[1] / "test_assets" / "soundtrack.mp3"
    if not audio_path.exists():
        raise AssertionError(f"Audio fixture is missing: {audio_path}")
    uploaded_audio = UPLOAD_DIR / "test_long_render_soundtrack.mp3"
    shutil.copyfile(audio_path, uploaded_audio)

    clips = [
        ClipConfig(
            id=f"long-{idx}",
            image_url=path,
            start_time=idx * 4.0,
            duration=4.0,
            motion="zoom_in" if idx % 2 == 0 else "zoom_out",
            transition="crossfade",
        )
        for idx, path in enumerate(test_images)
    ]
    plan = EditingPlan(
        duration_seconds=12.0,
        aspect_ratio="9:16",
        title={"enabled": False, "text": "", "gradient": ["#FFFFFF", "#CCCCCC"]},
        clips=clips,
        transitions=[
            TransitionConfig(
                id=f"long-transition-{idx}",
                from_clip_id=clips[idx].id,
                to_clip_id=clips[idx + 1].id,
                type="crossfade",
                duration=0.5,
                enabled=True,
            )
            for idx in range(len(clips) - 1)
        ],
    )

    job_id = start_render_job(plan, test_images, audio_filename=str(uploaded_audio))
    status = _wait_for_render(job_id)
    assert status.status == "completed", f"Long render failed: {status.error}"

    output_file = EXPORT_DIR / f"rayflow_{job_id}.mp4"
    duration = _probe_duration(output_file)
    assert duration >= 11.9, f"Rendered output was truncated at {duration:.2f}s"

    from app.core.config import FFMPEG_PATH
    decode = subprocess.run(
        [FFMPEG_PATH, "-v", "error", "-i", str(output_file), "-map", "0:v:0", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert decode.returncode == 0, decode.stderr
    probe = subprocess.run(
        [FFMPEG_PATH, "-hide_banner", "-i", str(output_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Audio:" in probe.stderr, probe.stderr[-500:]

if __name__ == "__main__":
    test_full_render_pipeline()
    test_long_render_with_transitions_and_audio()
    print("Renderer test passed!")
