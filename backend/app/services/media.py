"""Shared upload resolution and precise media metadata from FFprobe."""
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import UPLOAD_DIR, FFPROBE_PATH

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def uploaded_path(reference: str) -> Path:
    name = Path(unquote(urlparse(reference).path)).name
    path = UPLOAD_DIR / name
    if not name or not path.is_file():
        raise FileNotFoundError(f"Uploaded media is missing: {name or reference}")
    return path


def probe_streams(path: Path, count_frames: bool = False) -> dict:
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "error", *(["-count_frames"] if count_frames else []),
             "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("FFprobe is required. Install it on PATH or set FFPROBE_PATH.") from exc
    if result.returncode or result.stderr.strip():
        raise ValueError(f"Cannot probe media {path.name}: {result.stderr[-500:]}")
    return json.loads(result.stdout)


def _number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def stream_duration(stream: dict) -> float:
    if stream.get('duration_ts') is not None and stream.get('time_base'):
        return float(int(stream['duration_ts']) * Fraction(stream['time_base']))
    return _number(stream.get('duration'))


def probe_media(path: Path) -> dict:
    data = probe_streams(path)
    streams = data.get('streams', [])
    video = next((s for s in streams if s['codec_type'] == 'video' and
                  not s.get('disposition', {}).get('attached_pic')), {})
    audio = next((s for s in streams if s['codec_type'] == 'audio'), {})
    container = data.get('format', {})
    origin = _number(container.get('start_time'))
    # Include leading offsets and the longer A/V stream. Never estimate VFR
    # duration from frame count / nominal FPS, or round the source range.
    ends = [_number(s.get('start_time'), origin) - origin + stream_duration(s)
            for s in (video, audio) if stream_duration(s) > 0]
    duration = max(ends, default=_number(container.get('duration')))
    return {"duration": duration, "has_video": bool(video), "has_audio": bool(audio),
            "width": video.get('width', 0), "height": video.get('height', 0),
            "video_duration": stream_duration(video), "audio_duration": stream_duration(audio)}
