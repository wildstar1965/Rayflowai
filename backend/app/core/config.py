import os
import shutil
from pathlib import Path
import imageio_ffmpeg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Small local dotenv reader: never interpolate or log credentials. The backend
# file takes precedence over the legacy root file; process environment wins.
for env_file in (BASE_DIR / '.env', BASE_DIR.parent / '.env'):
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key and not key.startswith('#') and key.replace('_', '').isalnum():
                os.environ.setdefault(key, value.strip().strip('\"\''))
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
EXPORT_DIR = STORAGE_DIR / "exports"
CACHE_DIR = STORAGE_DIR / "cache"
ASSET_DIR = BASE_DIR / "assets"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Discover FFmpeg executable
try:
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = "ffmpeg"

# FFprobe is a companion executable, not included in imageio-ffmpeg's wheel.
FFPROBE_PATH = os.environ.get("FFPROBE_PATH") or shutil.which("ffprobe") or str(
    BASE_DIR / "tools" / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
)

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ORIGINS += [origin.strip() for origin in os.environ.get('CORS_ORIGINS', '').split(',') if origin.strip()]
