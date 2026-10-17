import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import EditingPlan, ClipConfig
from app.services.video_renderer import start_render_job, get_job_status

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
    for _ in range(60):
        status = get_job_status(job_id)
        print(f"Status: {status.status}, Progress: {status.progress:.1f}%")
        if status.status in ("completed", "failed"):
            break
        time.sleep(1.0)

    final_status = get_job_status(job_id)
    assert final_status.status == "completed", f"Render failed: {final_status.error}"
    assert final_status.progress == 100.0

    output_file = EXPORT_DIR / f"rayflow_{job_id}.mp4"
    assert output_file.exists(), f"Output file does not exist: {output_file}"
    file_size = output_file.stat().st_size
    print(f"Successfully rendered video! File size: {file_size} bytes ({output_file})")
    assert file_size > 10000, "Rendered video file is too small!"

if __name__ == "__main__":
    test_full_render_pipeline()
    print("Renderer test passed!")
