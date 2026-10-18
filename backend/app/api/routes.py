import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Query, Body, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PIL import Image, ImageOps
from app.services.media import uploaded_path, probe_media, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.schemas.editing_plan import TransitionConfig

from app.core.config import UPLOAD_DIR, EXPORT_DIR
from app.schemas.editing_plan import (
    EditingPlan,
    AudioAnalysisResult,
    CommandRequest,
    CommandResponse,
    RenderJobRequest,
    RenderJobStatus,
    ProjectPlanRequest,
    SubtitleSegment,
    VisualInsert,
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
def upload_images(files: List[UploadFile] = File(...)):
    """
    Uploads multiple photos for reel creation.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    saved_images = []
    destinations = []
    try:
        for file in files:
            ext = Path(file.filename or "").suffix.lower()
            if ext not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                raise ValueError(f"Unsupported media: {file.filename}. Use JPG, PNG, WebP, MP4, MOV or WebM.")
            clean_filename = f"media_{os.urandom(8).hex()}{ext}"
            destination = UPLOAD_DIR / clean_filename
            destinations.append(destination)
            with open(destination, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            media_type = "video" if ext in VIDEO_EXTENSIONS else "image"
            metadata = {}
            if media_type == "image":
                with Image.open(destination) as source:
                    source.load()
                    normalized = ImageOps.exif_transpose(source).convert("RGB")
                normalized.save(destination)
                metadata = {"width": normalized.width, "height": normalized.height}
            else:
                metadata = probe_media(destination)
                if not metadata["has_video"] or metadata["duration"] <= 0:
                    raise ValueError(f"Cannot decode video: {file.filename}")
            saved_images.append({
                "filename": clean_filename, "original_name": file.filename,
                "size": destination.stat().st_size, "url": f"/api/uploads/{clean_filename}",
                "media_type": media_type, **metadata,
            })
    except Exception as exc:
        for path in destinations:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Media upload failed: {exc}") from exc
    return {"images": saved_images, "count": len(saved_images)}

@router.post("/media/audio")
def upload_audio(file: UploadFile = File(...)):
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

    metadata = probe_media(destination)
    if not metadata["has_audio"] or metadata["duration"] <= 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file has no decodable audio.")

    return {
        "filename": clean_filename,
        "original_name": file.filename,
        "size": os.path.getsize(destination),
        "url": f"/api/uploads/{clean_filename}"
    }

@router.post("/media/demo-project")
def load_demo_project():
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
async def analyze_audio_endpoint(request: Request):
    """
    Performs beat tracking and tempo estimation using Librosa on an uploaded audio file.
    Supports Form data, JSON body, or Query parameters.
    """
    target = request.query_params.get('filename') or request.query_params.get('query_filename')
    try:
        body = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
        target = body.get('filename') or target
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail='Invalid audio analysis request.')
    if not target:
        raise HTTPException(status_code=400, detail="Audio filename is required.")

    audio_path = UPLOAD_DIR / Path(target).name
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")

    try:
        result = await run_in_threadpool(analyze_audio, str(audio_path))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio analysis failed: {str(e)}")

@router.post("/commands/interpret", response_model=CommandResponse)
def interpret_command_endpoint(request: CommandRequest):
    """
    Translates natural-language voice instructions into an updated EditingPlan.
    """
    if not request.command or not request.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty.")

    return interpret_command(request)

@router.post("/projects/plan", response_model=EditingPlan)
def create_or_update_plan(
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

    try:
        image_urls = [f"/api/uploads/{uploaded_path(f).name}" for f in actual_images]
        actual_plan.clips = build_timeline(image_urls, actual_plan, analysis_result)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actual_plan.transitions = [
        TransitionConfig(id=f"trans-{a.id}-{b.id}", from_clip_id=a.id, to_clip_id=b.id,
                         type=a.transition, duration=min(0.5, a.duration - 0.1, b.duration - 0.1),
                         enabled=a.transition not in ("none", "cut"))
        for a, b in zip(actual_plan.clips, actual_plan.clips[1:])
    ]
    return actual_plan

@router.post("/render")
async def render_video(request: RenderJobRequest):
    """
    Spawns an asynchronous FFmpeg rendering task for the specified EditingPlan.
    """
    if not request.plan.clips:
        raise HTTPException(status_code=400, detail="Add at least one clip to the timeline before exporting.")
    try:
        for clip in request.plan.clips:
            uploaded_path(clip.image_url)
        for insert in request.plan.visual_inserts:
            uploaded_path(insert.asset_url)
        if request.audio_filename:
            uploaded_path(request.audio_filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    status = get_job_status(job_id)
    if not file_path.exists() or (status and status.status != "completed"):
        raise HTTPException(status_code=404, detail="Rendered video not found or not yet complete.")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=output_filename
    )

class TranscribeRequest(BaseModel):
    media_filename: str
    model_size: Optional[str] = "base"
    language: Optional[str] = None

@router.post("/transcribe")
async def start_transcription(request: TranscribeRequest):
    """
    Initiates asynchronous speech-to-text transcription using local faster-whisper.
    """
    from app.services.speech_transcription import start_transcription_job

    media_path = UPLOAD_DIR / Path(request.media_filename).name
    if not media_path.exists():
        raise HTTPException(status_code=404, detail=f"Media file '{request.media_filename}' not found in uploads.")

    job_id = start_transcription_job(
        media_filename=request.media_filename,
        model_size=request.model_size or "base"
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Transcription job started."
    }

@router.get("/transcribe/{job_id}")
async def get_transcription_status(job_id: str):
    """
    Checks the status and results of a speech-to-text transcription job.
    """
    from app.services.speech_transcription import get_transcription_job

    job = get_transcription_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Transcription job not found.")
    return job

@router.get("/ollama/status")
def get_ollama_status_endpoint(host: Optional[str] = Query(default=None)):
    """
    Queries local Ollama availability, endpoint reachability, and installed model tags.
    """
    from app.services.ollama_client import check_ollama_status
    return check_ollama_status(host=host)

class OllamaInterpretRequest(BaseModel):
    command: str
    plan: EditingPlan
    model: Optional[str] = None
    host: Optional[str] = None

@router.post("/ollama/interpret", response_model=CommandResponse)
def interpret_with_ollama_endpoint(req: OllamaInterpretRequest):
    """
    Interprets natural language editing command using local Ollama model with deterministic fallback.
    """
    from app.services.ollama_client import interpret_with_ollama
    from app.services.command_interpreter import interpret_command

    # Common clip operations must use the full editor grammar first. The LLM's
    # restricted update schema cannot perform trims or reordering.
    fallback_req = CommandRequest(command=req.command, current_plan=req.plan)
    deterministic = interpret_command(fallback_req, allow_llm=False)
    if deterministic.applied_changes:
        return deterministic
    # Attempt Ollama structured interpretation
    res = interpret_with_ollama(command=req.command, current_plan=req.plan, model=req.model, host=req.host)
    if res:
        return res

    # Clean fallback to deterministic parser
    return deterministic

class SuggestInsertsRequest(BaseModel):
    subtitles: List[SubtitleSegment]
    available_assets: List[Dict[str, Any]]
    default_mode: Optional[str] = "pip"

@router.post("/inserts/suggest", response_model=List[VisualInsert])
async def suggest_inserts_endpoint(req: SuggestInsertsRequest):
    """
    Suggests contextual visual inserts (B-roll, PiP) matching transcript keywords.
    """
    from app.services.visual_inserts import suggest_contextual_inserts
    return suggest_contextual_inserts(
        subtitles=req.subtitles,
        available_assets=req.available_assets,
        default_mode=req.default_mode or "pip"
    )

class AutoEditRequest(BaseModel):
    media_filename: str
    style_key: Optional[str] = "fitness_energy"
    available_assets: Optional[List[Dict[str, Any]]] = None
    whisper_model: Optional[str] = "tiny"
    aspect_ratio: str = "9:16"
    include_captions: bool = True

@router.post("/auto-edit", response_model=EditingPlan)
def auto_edit_endpoint(req: AutoEditRequest):
    """
    Executes the end-to-end Auto Edit workflow from an uploaded video file.
    """
    from app.services.auto_edit import generate_auto_edit_reel
    try:
        return generate_auto_edit_reel(
            media_filename=req.media_filename, style_key=req.style_key or "fitness_energy",
            available_assets=req.available_assets, whisper_model=req.whisper_model or "tiny",
            aspect_ratio=req.aspect_ratio, include_captions=req.include_captions,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto Reel failed: {exc}") from exc
