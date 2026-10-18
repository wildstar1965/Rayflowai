"""Shared upload resolution and real media metadata (using the bundled FFmpeg)."""
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import UPLOAD_DIR, FFMPEG_PATH

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def uploaded_path(reference: str) -> Path:
    name = Path(unquote(urlparse(reference).path)).name
    path = UPLOAD_DIR / name
    if not name or not path.is_file():
        raise FileNotFoundError(f"Uploaded media is missing: {name or reference}")
    return path


def probe_media(path: Path) -> dict:
    result = subprocess.run(
        [FFMPEG_PATH, "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    duration = (int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])) if match else 0
    return {"duration": duration, "has_video": "Video:" in result.stderr,
            "has_audio": "Audio:" in result.stderr}
