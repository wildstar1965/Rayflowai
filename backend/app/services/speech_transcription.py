import os
import re
import uuid
import time
import threading
import subprocess
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.config import FFMPEG_PATH, UPLOAD_DIR, CACHE_DIR
from app.schemas.editing_plan import SubtitleSegment, WordTiming, SubtitleStyle
from app.services.processing import check_cancel, ProcessingCancelled

# Ensure HuggingFace Hub allows downloading public models without failing on expired local session tokens
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

# In-memory status registry for background transcription jobs
_TRANSCRIPTION_JOBS: Dict[str, Dict[str, Any]] = {}
_TRANSCRIBE_LOCK = threading.Lock()
_JOBS_LOCK = threading.Lock()
_CANCEL_EVENTS = {}

class TranscriptionError(RuntimeError):
    """A diagnostic safe to display without native model paths or stderr."""

@lru_cache(maxsize=2)
def _model(model_size, device='cpu', compute_type='int8'):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise TranscriptionError('Install local speech recognition: python -m pip install -r backend/requirements.txt') from None
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type,
                            local_files_only=os.getenv('WHISPER_LOCAL_ONLY', 'true').lower() != 'false')
    except Exception:
        raise TranscriptionError('Local Whisper could not load. Cache the selected model with backend/setup_local_assets.py --whisper MODEL; for unsupported hardware or memory errors use WHISPER_DEVICE=cpu, WHISPER_COMPUTE_TYPE=int8 and a smaller model.') from None


def source_fingerprint(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

# High-energy / emphasis keyword patterns common in reels and talking-head videos
EMPHASIS_KEYWORDS = {
    "secret", "proven", "mistake", "stop", "never", "always", "results", "power",
    "transform", "crucial", "massive", "faster", "easy", "simple", "hack", "best",
    "worst", "danger", "warning", "insane", "million", "billion", "money", "profit",
    "growth", "protein", "diet", "muscle", "workout", "fitness", "energy", "focus",
    "discipline", "strategy", "truth", "lies", "guaranteed", "unbelievable"
}

def extract_audio_from_media(media_path: str, output_wav_path: str, cancel=None) -> str:
    """
    Extracts high-quality 16kHz mono 16-bit PCM WAV audio from any video or audio file using FFmpeg.
    This provides the optimal sample rate and channel layout for Whisper models.
    """
    cmd = [
        FFMPEG_PATH,
        '-v', 'error', '-nostdin',
        "-y",
        "-i", media_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav_path
    ]
    check_cancel(cancel)
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while process.poll() is None:
            check_cancel(cancel)
            time.sleep(.1)
        if process.returncode != 0:
            raise TranscriptionError('Audio extraction failed. Check that the source contains a readable audio stream.')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
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
    language: Optional[str] = None,
    cancel=None,
) -> List[SubtitleSegment]:
    """
    Transcribes an audio file using faster-whisper on CPU with int8 quantization.
    Extracts word-level timestamps and maps output to SubtitleSegment schema.
    """
    digest = hashlib.sha256()
    digest.update(f'v3:{model_size}:{language}'.encode())
    with open(audio_path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            check_cancel(cancel)
            digest.update(chunk)
    cache_path = CACHE_DIR / f'transcript_{digest.hexdigest()}.json'
    # Serialize inference to avoid duplicate model work / CPU contention.
    while not _TRANSCRIBE_LOCK.acquire(timeout=.1):
        check_cancel(cancel)
    try:
        check_cancel(cancel)
        if cache_path.exists():
            try:
                return [SubtitleSegment.model_validate(s) for s in json.loads(cache_path.read_text(encoding='utf8'))]
            except (ValueError, OSError):
                pass
        try:
            result = (_transcribe_uncached(audio_path, model_size, language, cancel=cancel) if cancel is not None
                      else _transcribe_uncached(audio_path, model_size, language))
        except (ProcessingCancelled, TranscriptionError):
            raise
        except Exception:
            raise TranscriptionError('Local speech inference failed. Check the audio and available memory; try the tiny model with CPU int8 settings.') from None
        check_cancel(cancel)
        temp = cache_path.with_suffix('.part')
        try:
            temp.write_text(json.dumps([s.model_dump() for s in result]), encoding='utf8')
            temp.replace(cache_path)
        finally:
            temp.unlink(missing_ok=True)
        return result
    finally:
        _TRANSCRIBE_LOCK.release()

def _transcribe_uncached(audio_path, model_size, language, cancel=None):
    check_cancel(cancel)
    model = _model(model_size, os.getenv('WHISPER_DEVICE', 'cpu'), os.getenv('WHISPER_COMPUTE_TYPE', 'int8'))

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=True,
        language=language
    )

    result_subtitles: List[SubtitleSegment] = []
    default_style = SubtitleStyle(preset="bold_pop")

    for idx, seg in enumerate(segments):
        check_cancel(cancel)
        start = max(0, float(seg.start), result_subtitles[-1].end_time if result_subtitles else 0)
        end = float(seg.end)
        if not seg.text.strip() or end <= start:
            continue
        words: List[WordTiming] = []
        if hasattr(seg, "words") and seg.words:
            for w in seg.words:
                word_start = max(start, float(w.start), words[-1].end if words else start)
                word_end = min(end, float(w.end))
                if word_end <= word_start or not w.word.strip():
                    continue
                words.append(WordTiming(
                    word=w.word.strip(),
                    start=word_start,
                    end=word_end
                ))

        # Apply emphasis styling to key words
        words = apply_word_emphasis(words, default_style)

        if not seg.text.strip() or seg.end <= seg.start:
            continue
        words = [w for w in words if w.end > w.start and w.word]
        result_subtitles.append(SubtitleSegment(
            id=f"sub-{idx + 1}",
            text=seg.text.strip(),
            start_time=start,
            end_time=end,
            words=words,
            style=default_style
        ))

    return result_subtitles

def _transcription_worker(job_id: str, media_filename: str, model_size: str, language=None):
    """
    Background worker thread to transcribe media without freezing the server.
    """
    job = _TRANSCRIPTION_JOBS[job_id]
    wav_path = None
    cancel = _CANCEL_EVENTS[job_id]
    started = time.monotonic()
    try:
        check_cancel(cancel)
        job["status"] = "processing"
        job["progress"] = 10.0

        media_path = UPLOAD_DIR / Path(media_filename).name
        if not media_path.exists():
            raise TranscriptionError('Source media is no longer available in uploads.')
        fingerprint = source_fingerprint(media_path)

        job["progress"] = 25.0
        # If media is video or needs audio conversion, extract 16kHz WAV
        suffix = media_path.suffix.lower()
        if suffix in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4a", ".aac", ".ogg", ".flac"):
            wav_path = UPLOAD_DIR / f"temp_{job_id}.wav"
            extract_audio_from_media(str(media_path), str(wav_path), cancel=cancel)
            target_audio = str(wav_path)
            is_temp_wav = True
        else:
            target_audio = str(media_path)
            is_temp_wav = False

        job["progress"] = 50.0

        # Execute transcription with word-level timestamps
        subtitles = transcribe_audio_file(target_audio, model_size=model_size, language=language, cancel=cancel)
        check_cancel(cancel)
        if fingerprint != source_fingerprint(media_path):
            raise TranscriptionError('Source media changed during transcription. Generate captions again.')
        for segment in subtitles:
            segment.source_filename = media_path.name
            segment.origin = 'auto'
        job["progress"] = 90.0

        job["subtitles"] = [s.model_dump() for s in subtitles]
        job['source_fingerprint'] = fingerprint
        job["status"] = "completed"
        job["progress"] = 100.0

        # Cleanup temp WAV if created
        if is_temp_wav and os.path.exists(target_audio):
            try:
                os.remove(target_audio)
            except Exception:
                pass

    except ProcessingCancelled:
        job['status'] = 'cancelled'
        job['subtitles'] = []
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e) if isinstance(e, TranscriptionError) else 'Local transcription failed. Check the source audio, available memory and local model configuration.'
        job["progress"] = 0.0
    finally:
        job['elapsed_seconds'] = round(time.monotonic() - started, 3)
        _CANCEL_EVENTS.pop(job_id, None)
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)

def start_transcription_job(media_filename: str, model_size: str = "base", language=None) -> str:
    """
    Starts an asynchronous speech recognition job for uploaded video or audio.
    """
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        if sum(j['status'] in ('queued', 'processing') for j in _TRANSCRIPTION_JOBS.values()) >= 4:
            raise ValueError('The local transcription queue is full. Wait for or cancel an active job.')
        for key, job in list(_TRANSCRIPTION_JOBS.items()):
            if job['status'] not in ('queued', 'processing') and time.time() - job['created_at'] > 3600:
                _TRANSCRIPTION_JOBS.pop(key, None)
        _CANCEL_EVENTS[job_id] = threading.Event()
        _TRANSCRIPTION_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
            "subtitles": [],
            "created_at": time.time(),
            "error": None,
            'source_filename': Path(media_filename).name,
        }

    t = threading.Thread(
        target=_transcription_worker,
        args=(job_id, media_filename, model_size, language),
        daemon=True
    )
    t.start()
    return job_id

def get_transcription_job(job_id: str) -> Optional[Dict[str, Any]]:
    return _TRANSCRIPTION_JOBS.get(job_id)


def cancel_transcription_job(job_id):
    event = _CANCEL_EVENTS.get(job_id)
    if event is None:
        return False
    event.set()
    _TRANSCRIPTION_JOBS[job_id]['status'] = 'cancelled'
    return True
