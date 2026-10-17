import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Query, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import (
    EditingPlan,
    AudioAnalysisResult,
    CommandRequest,
    CommandResponse,
    RenderJobRequest,
    RenderJobStatus,
    ProjectPlanRequest,
)
from app.services.audio_analysis import analyze_audio
from app.services.timeline_builder import build_timeline
from app.services.command_interpreter import interpret_command
from app.services.video_renderer import start_render_job, get_job_status

router = APIRouter(prefix="/api")

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "RayFlow AI Cinematic Video Engine",
        "version": "1.0.0"
    }

@router.post("/media/images")
async def upload_images(files: List[UploadFile] = File(...)):
    """
    Uploads multiple photos for reel creation.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    saved_images = []
    for file in files:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            continue

        clean_filename = f"{Path(file.filename).stem}_{os.urandom(4).hex()}{ext}"
        destination = UPLOAD_DIR / clean_filename

        with open(destination, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        size_bytes = os.path.getsize(destination)
        saved_images.append({
            "filename": clean_filename,
            "original_name": file.filename,
            "size": size_bytes,
            "url": f"/api/uploads/{clean_filename}"
        })

    if not saved_images:
        raise HTTPException(status_code=400, detail="No supported image files found (.jpg, .png, .webp).")

    return {"images": saved_images, "count": len(saved_images)}

@router.post("/media/audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    Uploads a background music track.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. Please upload an .mp3, .wav, or .m4a file."
        )

    clean_filename = f"audio_{os.urandom(4).hex()}{ext}"
    destination = UPLOAD_DIR / clean_filename

    with open(destination, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "filename": clean_filename,
        "original_name": file.filename,
        "size": os.path.getsize(destination),
        "url": f"/api/uploads/{clean_filename}"
    }

@router.post("/media/demo-project")
async def load_demo_project():
    """
    Sets up 4 sample images and a sample soundtrack in uploads,
    enabling instant loading of a 4-photo project in the studio editor.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    saved_images = []
    colors = [
        (45, 55, 72),
        (59, 130, 246),
        (16, 185, 129),
        (245, 158, 11)
    ]
    for i in range(4):
        fn = f"demo_photo_{i}.jpg"
        dest = UPLOAD_DIR / fn
        if not dest.exists():
            src = Path(f"test_assets/test_img_{i}.jpg")
            if src.exists():
                shutil.copyfile(src, dest)
            else:
                img = Image.new("RGB", (1080, 1920), color=colors[i % len(colors)])
                draw = ImageDraw.Draw(img)
                draw.text((360, 960), f"RayFlow Photo {i+1}", fill="white")
                img.save(dest, "JPEG")
        saved_images.append({
            "filename": fn,
            "original_name": f"RayFlow Photo {i+1}.jpg",
            "size": os.path.getsize(dest),
            "url": f"/api/uploads/{fn}"
        })

    audio_fn = "demo_soundtrack.mp3"
    audio_dest = UPLOAD_DIR / audio_fn
    if not audio_dest.exists():
        src_audio = Path("test_assets/soundtrack.mp3")
        if src_audio.exists():
            shutil.copyfile(src_audio, audio_dest)
        else:
            # Check for any existing mp3 in storage
            for mp3_cand in UPLOAD_DIR.glob("*.mp3"):
                shutil.copyfile(mp3_cand, audio_dest)
                break

    saved_audio = None
    if audio_dest.exists():
        saved_audio = {
            "filename": audio_fn,
            "original_name": "Cinematic Soundtrack.mp3",
            "size": os.path.getsize(audio_dest),
            "url": f"/api/uploads/{audio_fn}"
        }

    return {
        "images": saved_images,
        "audio": saved_audio
    }


class AudioAnalyzeRequest(BaseModel):
    filename: str

@router.post("/audio/analyze", response_model=AudioAnalysisResult)
async def analyze_audio_endpoint(
    filename: Optional[str] = Form(default=None),
    json_req: Optional[AudioAnalyzeRequest] = Body(default=None),
    query_filename: Optional[str] = Query(default=None)
):
    """
    Performs beat tracking and tempo estimation using Librosa on an uploaded audio file.
    Supports Form data, JSON body, or Query parameters.
    """
    target = filename or (json_req.filename if json_req else None) or query_filename
    if not target:
        raise HTTPException(status_code=400, detail="Audio filename is required.")

    audio_path = UPLOAD_DIR / Path(target).name
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")

    try:
        result = analyze_audio(str(audio_path))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio analysis failed: {str(e)}")

@router.post("/commands/interpret", response_model=CommandResponse)
async def interpret_command_endpoint(request: CommandRequest):
    """
    Translates natural-language voice instructions into an updated EditingPlan.
    """
    if not request.command or not request.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty.")

    return interpret_command(request)

@router.post("/projects/plan", response_model=EditingPlan)
async def create_or_update_plan(
    request: Optional[ProjectPlanRequest] = None,
    image_filenames: Optional[List[str]] = Query(default=None),
    audio_filename: Optional[str] = Query(default=None)
):
    """
    Constructs a synchronized timeline connecting images, music beats, and stylistic pacing.
    Accepts ProjectPlanRequest JSON body, or Query parameters.
    """
    actual_plan = (request.plan if request and request.plan else EditingPlan())
    actual_images = (request.image_filenames if request and request.image_filenames else image_filenames) or []
    actual_audio = (request.audio_filename if request and request.audio_filename else audio_filename)

    analysis_result = None
    if actual_audio:
        audio_path = UPLOAD_DIR / Path(actual_audio).name
        if audio_path.exists():
            try:
                analysis_result = analyze_audio(str(audio_path))
            except Exception:
                analysis_result = None

    image_urls = [f"/api/uploads/{Path(f).name}" for f in actual_images]
    actual_plan.clips = build_timeline(image_urls, actual_plan, analysis_result)
    return actual_plan

@router.post("/render")
async def render_video(request: RenderJobRequest):
    """
    Spawns an asynchronous FFmpeg rendering task for the specified EditingPlan.
    """
    if not request.image_filenames:
        raise HTTPException(status_code=400, detail="At least one image is required for rendering.")

    job_id = start_render_job(
        plan=request.plan,
        image_filenames=request.image_filenames,
        audio_filename=request.audio_filename
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Render job initiated."
    }

@router.get("/render/{job_id}", response_model=RenderJobStatus)
async def get_render_job(job_id: str):
    """
    Checks the status and progress of a rendering job.
    """
    status = get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Render job not found.")
    return status

@router.get("/render/{job_id}/download")
async def download_rendered_video(job_id: str):
    """
    Downloads the rendered MP4 file.
    """
    output_filename = f"rayflow_{job_id}.mp4"
    file_path = EXPORT_DIR / output_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Rendered video not found or not yet complete.")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=output_filename
    )
