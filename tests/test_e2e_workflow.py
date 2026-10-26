import os
import sys
import time
import wave
import struct
import math
from pathlib import Path
from PIL import Image, ImageDraw

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import EditingPlan, CommandRequest

client = TestClient(app)

def create_dummy_audio(path: Path, duration: float = 4.0, sample_rate: int = 22050):
    """Generates a simple tone WAV file with simulated beats."""
    n_samples = int(duration * sample_rate)
    with wave.open(str(path), 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        for i in range(n_samples):
            t = i / sample_rate
            # 2 Hz rhythm pulse + 440 Hz tone
            pulse = (math.sin(2 * math.pi * 2.0 * t) > 0.8)
            amplitude = 16000 if pulse else 4000
            val = int(amplitude * math.sin(2 * math.pi * 440.0 * t))
            data = struct.pack('<h', max(-32768, min(32767, val)))
            wav_file.writeframesraw(data)

def test_full_e2e_workflow(tmp_path):
    assert client.post('/api/session').status_code == 200
    print("=== Step 1: Health Check ===")
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    print("Health check OK:", res.json())

    print("\n=== Step 2: Upload Multiple Images ===")
    test_img_paths = []
    colors = [(240, 240, 245), (20, 20, 25), (100, 100, 110)]
    for i, col in enumerate(colors):
        p = tmp_path / f"e2e_photo_{i}.jpg"
        img = Image.new("RGB", (720, 1280), col)
        draw = ImageDraw.Draw(img)
        draw.text((100, 600), f"E2E TEST PHOTO {i+1}", fill=(255, 255, 255) if col[0] < 128 else (0, 0, 0))
        img.save(p, "JPEG")
        test_img_paths.append(p)

    files = [
        ("files", (p.name, open(p, "rb"), "image/jpeg")) for p in test_img_paths
    ]
    res_upload_img = client.post("/api/media/images", files=files)
    assert res_upload_img.status_code == 200, res_upload_img.text
    uploaded_images = res_upload_img.json()["images"]
    assert len(uploaded_images) == 3
    print(f"Uploaded {len(uploaded_images)} images successfully.")

    print("\n=== Step 3: Upload Soundtrack & Audio Analysis ===")
    audio_path = tmp_path / "e2e_beat_track.wav"
    create_dummy_audio(audio_path, duration=4.5)
    
    with open(audio_path, "rb") as af:
        res_audio = client.post("/api/media/audio", files={"file": ("e2e_beat_track.wav", af, "audio/wav")})
    assert res_audio.status_code == 200, res_audio.text
    audio_info = res_audio.json()
    print("Uploaded audio:", audio_info["original_name"])

    # Beat analysis
    res_analysis = client.post("/api/audio/analyze", data={"filename": audio_info["filename"]})
    assert res_analysis.status_code == 200, res_analysis.text
    analysis_data = res_analysis.json()
    print(f"Beat analysis: Tempo={analysis_data['tempo']} BPM, Beats={analysis_data['beat_count']}")
    assert analysis_data["beat_count"] > 0

    print("\n=== Step 4: Timeline Generation ===")
    plan = EditingPlan(duration_seconds=4.5, style="cinematic", cut_pacing="balanced", beat_sync=True)
    plan_payload = {
        "plan": plan.model_dump(),
        "image_filenames": [img["filename"] for img in uploaded_images],
        "audio_filename": audio_info["filename"]
    }
    res_plan = client.post("/api/projects/plan", json=plan_payload)
    assert res_plan.status_code == 200, res_plan.text
    generated_plan = res_plan.json()
    assert len(generated_plan["clips"]) >= 3
    print(f"Timeline plan generated with {len(generated_plan['clips'])} synchronized clips.")

    print("\n=== Step 5: Natural Language Directives ===")
    commands_to_test = [
        ("Create a 20-second cinematic reel.", lambda p: p.duration_seconds == 20.0 and p.style == "cinematic"),
        ("Sync the cuts to the beats.", lambda p: p.beat_sync is True),
        ("Make the first photo last three seconds.", lambda p: len(p.clips) > 0 and p.clips[0].duration == 3.0),
        # Titles appear at the beginning in time; position is a spatial setting.
        ("Add a title at the beginning.", lambda p: p.title.enabled is True and p.title.position == "center"),
        ("Make the transitions smoother.", lambda p: p.clips[0].transition == "crossfade"),
        ("Change the title to Summer Memories.", lambda p: p.title.text == "Summer Memories"),
    ]

    current_test_plan = EditingPlan.model_validate(generated_plan)
    for cmd_text, validator in commands_to_test:
        req = CommandRequest(command=cmd_text, current_plan=current_test_plan)
        res_cmd = client.post("/api/commands/interpret", json=req.model_dump())
        assert res_cmd.status_code == 200, res_cmd.text
        resp_data = res_cmd.json()
        updated_plan = EditingPlan.model_validate(resp_data["plan"])
        assert validator(updated_plan), f"Validation failed for command: '{cmd_text}'"
        print(f"Directive OK: '{cmd_text}' -> {resp_data['applied_changes']}")
        current_test_plan = updated_plan

    print("\n=== Step 6: Full FFmpeg MP4 Render & Export ===")
    # Set final plan for quick 3.0s test render
    render_plan = EditingPlan(
        duration_seconds=3.0,
        aspect_ratio="9:16",
        style="cinematic",
        title={"enabled": True, "text": "RAYFLOW CINEMA", "gradient": ["#FFFFFF", "#CCCCCC"]},
        clips=[
            {"id": "c1", "image_url": uploaded_images[0]['url'], "start_time": 0.0, "duration": 1.5, "motion": "zoom_in", "transition": "crossfade"},
            {"id": "c2", "image_url": uploaded_images[1]['url'], "start_time": 1.5, "duration": 1.5, "motion": "zoom_out", "transition": "crossfade"},
        ]
    )

    render_req = {
        "plan": render_plan.model_dump(),
        "image_filenames": [image['filename'] for image in uploaded_images[:2]],
        "audio_filename": audio_info["filename"]
    }
    res_render = client.post("/api/render", json=render_req)
    assert res_render.status_code == 200, res_render.text
    job_id = res_render.json()["job_id"]
    print(f"Render job initiated: {job_id}")

    # Poll status
    for _ in range(60):
        status_res = client.get(f"/api/render/{job_id}")
        assert status_res.status_code == 200
        st = status_res.json()
        print(f"Status: {st['status']}, Progress: {st['progress']:.1f}%")
        if st["status"] in ("completed", "failed"):
            break
        time.sleep(1.0)

    final_res = client.get(f"/api/render/{job_id}")
    final_data = final_res.json()
    assert final_data["status"] == "completed", f"Render failed: {final_data.get('error')}"
    assert final_data["progress"] == 100.0

    # Download check
    download_res = client.get(f"/api/render/{job_id}/download")
    assert download_res.status_code == 200
    video_bytes = len(download_res.content)
    print(f"Downloaded rendered MP4! Total size: {video_bytes} bytes.")
    assert video_bytes > 15000, "Rendered video is too small!"

    print("\nSUCCESS! All End-to-End Workflow Verification Steps Passed Successfully!")

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        test_full_e2e_workflow(Path(directory))
