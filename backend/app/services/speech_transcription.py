import os
import re
import uuid
import time
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.config import FFMPEG_PATH, UPLOAD_DIR
from app.schemas.editing_plan import SubtitleSegment, WordTiming, SubtitleStyle

# Ensure HuggingFace Hub allows downloading public models without failing on expired local session tokens
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

# In-memory status registry for background transcription jobs
_TRANSCRIPTION_JOBS: Dict[str, Dict[str, Any]] = {}

# High-energy / emphasis keyword patterns common in reels and talking-head videos
EMPHASIS_KEYWORDS = {
    "secret", "proven", "mistake", "stop", "never", "always", "results", "power",
    "transform", "crucial", "massive", "faster", "easy", "simple", "hack", "best",
    "worst", "danger", "warning", "insane", "million", "billion", "money", "profit",
    "growth", "protein", "diet", "muscle", "workout", "fitness", "energy", "focus",
    "discipline", "strategy", "truth", "lies", "guaranteed", "unbelievable"
}

def extract_audio_from_media(media_path: str, output_wav_path: str) -> str:
    """
    Extracts high-quality 16kHz mono 16-bit PCM WAV audio from any video or audio file using FFmpeg.
    This provides the optimal sample rate and channel layout for Whisper models.
    """
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", media_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to extract audio from {media_path}: {res.stderr[-300:] if res.stderr else 'unknown error'}")
    return output_wav_path

def apply_word_emphasis(words: List[WordTiming], style: SubtitleStyle) -> List[WordTiming]:
    """
    Identifies impactful emphasis words based on:
    1. Capitalization or numbers (e.g. '100%', '3X', 'IMPORTANT')
    2. High-energy keywords from creator reels
    3. Words with longer relative duration (stressed syllables)
    """
    if not words:
        return words

    avg_duration = sum(w.end - w.start for w in words) / max(1, len(words))

    for w in words:
        clean_word = re.sub(r'[^a-zA-Z0-9]', '', w.word).lower()
        raw_word = w.word.strip()
        dur = w.end - w.start

        is_keyword = clean_word in EMPHASIS_KEYWORDS
        is_all_caps = len(raw_word) > 1 and raw_word.isupper()
        is_number = bool(re.search(r'\d', raw_word))
        is_extended_stress = dur > (avg_duration * 1.55) and len(clean_word) >= 4

        if is_keyword or is_all_caps or is_number or is_extended_stress:
            w.emphasis = True
            w.color = style.highlight_color
            w.size_multiplier = 1.25
        else:
            w.emphasis = False
            w.color = None
            w.size_multiplier = 1.0

    return words

def transcribe_audio_file(
    audio_path: str,
    model_size: str = "base",
    language: Optional[str] = None
) -> List[SubtitleSegment]:
    """
    Transcribes an audio file using faster-whisper on CPU with int8 quantization.
    Extracts word-level timestamps and maps output to SubtitleSegment schema.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed or available. Please install it with 'pip install faster-whisper'."
        )

    # Use CPU with int8 quantization for ultra-fast, low-RAM local execution
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=True,
        language=language
    )

    result_subtitles: List[SubtitleSegment] = []
    default_style = SubtitleStyle(preset="bold_pop")

    for idx, seg in enumerate(segments):
        words: List[WordTiming] = []
        if hasattr(seg, "words") and seg.words:
            for w in seg.words:
                words.append(WordTiming(
                    word=w.word.strip(),
                    start=round(w.start, 2),
                    end=round(w.end, 2)
                ))

        # Apply emphasis styling to key words
        words = apply_word_emphasis(words, default_style)

        result_subtitles.append(SubtitleSegment(
            id=f"sub-{idx + 1}",
            text=seg.text.strip(),
            start_time=round(seg.start, 2),
            end_time=round(seg.end, 2),
            words=words,
            style=default_style
        ))

    return result_subtitles

def _transcription_worker(job_id: str, media_filename: str, model_size: str):
    """
    Background worker thread to transcribe media without freezing the server.
    """
    job = _TRANSCRIPTION_JOBS[job_id]
    wav_path = None
    try:
        job["status"] = "processing"
        job["progress"] = 10.0

        media_path = UPLOAD_DIR / Path(media_filename).name
        if not media_path.exists():
            raise FileNotFoundError(f"Media file {media_filename} does not exist in uploads.")

        job["progress"] = 25.0
        # If media is video or needs audio conversion, extract 16kHz WAV
        suffix = media_path.suffix.lower()
        if suffix in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4a", ".aac", ".ogg", ".flac"):
            wav_path = UPLOAD_DIR / f"temp_{job_id}.wav"
            extract_audio_from_media(str(media_path), str(wav_path))
            target_audio = str(wav_path)
            is_temp_wav = True
        else:
            target_audio = str(media_path)
            is_temp_wav = False

        job["progress"] = 50.0

        # Execute transcription with word-level timestamps
        subtitles = transcribe_audio_file(target_audio, model_size=model_size)
        job["progress"] = 90.0

        job["subtitles"] = [s.model_dump() for s in subtitles]
        job["status"] = "completed"
        job["progress"] = 100.0

        # Cleanup temp WAV if created
        if is_temp_wav and os.path.exists(target_audio):
            try:
                os.remove(target_audio)
            except Exception:
                pass

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["progress"] = 0.0
    finally:
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)

def start_transcription_job(media_filename: str, model_size: str = "base") -> str:
    """
    Starts an asynchronous speech recognition job for uploaded video or audio.
    """
    job_id = str(uuid.uuid4())[:8]
    _TRANSCRIPTION_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "subtitles": [],
        "created_at": time.time(),
        "error": None
    }

    t = threading.Thread(
        target=_transcription_worker,
        args=(job_id, media_filename, model_size),
        daemon=True
    )
    t.start()
    return job_id

def get_transcription_job(job_id: str) -> Optional[Dict[str, Any]]:
    return _TRANSCRIPTION_JOBS.get(job_id)
