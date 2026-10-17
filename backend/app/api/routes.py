import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse

from app.core.config import UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import (
    EditingPlan,
    AudioAnalysisResult,
    CommandRequest,
    CommandResponse,
    RenderJobRequest,
    RenderJobStatus,
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

@router.post("/audio/analyze", response_model=AudioAnalysisResult)
async def analyze_audio_endpoint(filename: str = Form(...)):
    """
    Performs beat tracking and tempo estimation using Librosa on an uploaded audio file.
    """
    audio_path = UPLOAD_DIR / Path(filename).name
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
    plan: EditingPlan,
    image_filenames: List[str],
    audio_filename: Optional[str] = None
):
    """
    Constructs a synchronized timeline connecting images, music beats, and stylistic pacing.
    """
    analysis_result = None
    if audio_filename:
        audio_path = UPLOAD_DIR / Path(audio_filename).name
        if audio_path.exists():
            try:
                analysis_result = analyze_audio(str(audio_path))
            except Exception:
                analysis_result = None

    image_urls = [f"/api/uploads/{Path(f).name}" for f in image_filenames]
    plan.clips = build_timeline(image_urls, plan, analysis_result)
    return plan

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
