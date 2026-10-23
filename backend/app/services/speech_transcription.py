import os
import re
import uuid
import time
import threading
from app.editor.context import scoped_target, workspace_id
import subprocess
import hashlib
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.config import FFMPEG_PATH, UPLOAD_DIR, CACHE_DIR
from app.schemas.editing_plan import SubtitleSegment, WordTiming, SubtitleStyle
from app.services.processing import check_cancel, ProcessingCancelled
from app.services.speech_models import (
    WHISPER_MODELS, TranscriptionError, load_model as _model, INFERENCE_LOCK,
    default_model, runtime_for,
)

# Ensure HuggingFace Hub allows downloading public models without failing on expired local session tokens
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

# In-memory status registry for background transcription jobs
_TRANSCRIPTION_JOBS: Dict[str, Dict[str, Any]] = {}
_TRANSCRIBE_LOCK = INFERENCE_LOCK
_JOBS_LOCK = threading.Lock()
_CANCEL_EVENTS = {}

# Only library model IDs may be supplied by a client, never filesystem paths.


def validate_transcription_options(model_size, language):
    if model_size not in WHISPER_MODELS:
        raise ValueError('Choose a supported local Whisper model.')
    from faster_whisper.tokenizer import _LANGUAGE_CODES
    if language and language not in _LANGUAGE_CODES:
        raise ValueError('Unsupported Whisper language code. Use auto-detect or a supported language.')


def transcription_source(filename):
    from app.services.media import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
    if not filename or Path(filename).name != filename or any(c in filename for c in '/\\:%'):
        raise ValueError('Choose an uploaded media filename, not a path or URL.')
    root = UPLOAD_DIR.resolve()
    path = (root / filename).resolve()
    if path.parent != root:
        raise ValueError('Source must be inside uploads.')
    if path.suffix.lower() not in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS:
        raise ValueError('Choose a supported audio or video file.')
    if not path.is_file():
        raise FileNotFoundError('Source media is no longer available in uploads.')
    return path

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
            w.size_multiplier = 1.0
        else:
            w.emphasis = False
            w.color = None
            w.size_multiplier = 1.0

    return words

def transcribe_audio_file(
    audio_path: str,
    model_size: str = None,
    language: Optional[str] = None,
    cancel=None,
    report=None,
) -> List[SubtitleSegment]:
    """
    Transcribes using local faster-whisper on the selected CPU or CUDA runtime.
    Extracts word-level timestamps and maps output to SubtitleSegment schema.
    """
    digest = hashlib.sha256()
    model_size = model_size or default_model()
    validate_transcription_options(model_size, language)
    digest.update(f'v5:{model_size}:{language}'.encode())
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
                cached = [SubtitleSegment.model_validate(s) for s in json.loads(cache_path.read_text(encoding='utf8'))]
                if report:
                    detected = next((w.language for s in cached for w in s.words if w.language), language)
                    report(90, 'Using cached transcript', detected)
                return cached
            except (ValueError, OSError):
                pass
        try:
            options = {'cancel': cancel} if cancel is not None else {}
            if report is not None:
                options['report'] = report
            result = _transcribe_uncached(audio_path, model_size, language, **options)
        except (ProcessingCancelled, TranscriptionError):
            raise
        except Exception:
            raise TranscriptionError('Local speech inference failed. Check available memory and CPU/int8 settings, or explicitly cache and select Small. No smaller model was substituted.') from None
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

def _transcribe_uncached(audio_path, model_size, language, cancel=None, report=None):
    check_cancel(cancel)
    if report:
        report(35, 'Loading local speech model', language)
    model = _model(model_size)

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=True,
        language=language
    )

    result_subtitles: List[SubtitleSegment] = []
    default_style = SubtitleStyle(preset="bold_pop")
    detected = getattr(info, 'language', language)
    duration = max(.001, getattr(info, 'duration', 0) or 0)
    if report:
        report(40, 'Transcribing speech', detected)

    for idx, seg in enumerate(segments):
        check_cancel(cancel)
        start = max(0, float(seg.start), result_subtitles[-1].end_time if result_subtitles else 0)
        end = float(seg.end)
        if not math.isfinite(start) or not math.isfinite(end) or not seg.text.strip() or end <= start:
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
                    end=word_end,
                    confidence=getattr(w, 'probability', None),
                    language=detected,
                ))

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
        if report:
            report(min(89, 40 + 49 * end / duration), 'Transcribing speech', detected)

    return result_subtitles

def _transcription_worker(job_id: str, media_filename: str, model_size: str, language=None):
    """
    Background worker thread to transcribe media without freezing the server.
    """
    job = _TRANSCRIPTION_JOBS[job_id]
    from app.services import job_history
    wav_path = None
    cancel = _CANCEL_EVENTS[job_id]
    started = time.monotonic()
    try:
        check_cancel(cancel)
        job["status"] = "processing"
        job_history.started(job_id)
        job["progress"] = 10.0
        job['stage'] = 'Reading source media'

        media_path = transcription_source(media_filename)
        fingerprint = source_fingerprint(media_path)

        job["progress"] = 25.0
        job['stage'] = 'Extracting speech audio'
        # If media is video or needs audio conversion, extract 16kHz WAV
        suffix = media_path.suffix.lower()
        if suffix != '.wav':
            wav_path = UPLOAD_DIR / f"temp_{job_id}.wav"
            extract_audio_from_media(str(media_path), str(wav_path), cancel=cancel)
            target_audio = str(wav_path)
            is_temp_wav = True
        else:
            target_audio = str(media_path)
            is_temp_wav = False

        def report(progress, stage, detected):
            check_cancel(cancel)
            job.update(progress=round(progress, 1), stage=stage, language=detected, **runtime_for(model_size))

        # Execute transcription with word-level timestamps
        subtitles = transcribe_audio_file(target_audio, model_size=model_size, language=language, cancel=cancel, report=report)
        from app.services.caption_engine import readable_segments
        subtitles = readable_segments(subtitles)
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
        job['stage'] = 'Captions ready' if subtitles else 'No speech detected'

        # Cleanup temp WAV if created
        if is_temp_wav and os.path.exists(target_audio):
            try:
                os.remove(target_audio)
            except Exception:
                pass

    except ProcessingCancelled:
        job['status'] = 'cancelled'
        job['stage'] = 'Cancelled'
        job['subtitles'] = []
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e) if isinstance(e, TranscriptionError) else 'Local transcription failed. Check the source audio, available memory and local model configuration.'
        job["progress"] = 0.0
    finally:
        job['elapsed_seconds'] = round(time.monotonic() - started, 3)
        job_history.finished(job_id, job['status'])
        _CANCEL_EVENTS.pop(job_id, None)
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)

def start_transcription_job(media_filename: str, model_size: str = None, language=None) -> str:
    """
    Starts an asynchronous speech recognition job for uploaded video or audio.
    """
    model_size = model_size or default_model()
    validate_transcription_options(model_size, language)
    transcription_source(media_filename)
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
            'model': model_size, 'provider': 'faster-whisper', 'language': language,
            'stage': 'Queued',
        }

    from app.services import job_history
    job_history.created(job_id, 'transcription')
    t = threading.Thread(
        target=scoped_target(_transcription_worker),
        args=(job_id, media_filename, model_size, language),
        daemon=True
    )
    t.start()
    return job_id

def get_transcription_job(job_id: str) -> Optional[Dict[str, Any]]:
    from app.services import job_history
    if workspace_id.get() and not job_history.get(job_id):
        return None
    return _TRANSCRIPTION_JOBS.get(job_id)


def cancel_transcription_job(job_id):
    from app.services import job_history
    if workspace_id.get() and not job_history.get(job_id):
        return False
    event = _CANCEL_EVENTS.get(job_id)
    if event is None:
        return False
    event.set()
    _TRANSCRIPTION_JOBS[job_id]['status'] = 'cancelled'
    return True
