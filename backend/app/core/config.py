import os
import shutil
from pathlib import Path
import imageio_ffmpeg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Small local dotenv reader: never interpolate or log credentials. The backend
# file takes precedence over the legacy root file; process environment wins.
env_files = () if os.getenv('RAYFLOW_ENV') == 'production' else (BASE_DIR / '.env', BASE_DIR.parent / '.env')
for env_file in env_files:
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key and not key.startswith('#') and key.replace('_', '').isalnum():
                os.environ.setdefault(key, value.strip().strip('\"\''))
ENVIRONMENT = os.getenv('RAYFLOW_ENV', 'development')
if ENVIRONMENT not in ('development', 'test', 'production'):
    raise ValueError('RAYFLOW_ENV must be development, test, or production.')
if ENVIRONMENT == 'production' and env_files:
    raise ValueError('Set RAYFLOW_ENV=production in the process environment before startup, not in a local dotenv file.')


def positive_int(name, default, maximum):
    try:
        value = int(os.getenv(name, str(default)))
        if not 1 <= value <= maximum:
            raise ValueError()
        return value
    except ValueError:
        raise ValueError(f'{name} must be an integer between 1 and {maximum}.') from None


MAX_UPLOAD_MB = positive_int('MAX_UPLOAD_MB', 500, 10000)
MAX_REQUEST_MB = positive_int('MAX_REQUEST_MB', 1024, 20000)
RENDER_CONCURRENCY = positive_int('RENDER_CONCURRENCY', 1, 8)
RENDER_QUEUE_LIMIT = positive_int('RENDER_QUEUE_LIMIT', 4, 100)
RENDER_TIMEOUT_SECONDS = positive_int('RENDER_TIMEOUT_SECONDS', 1800, 86400)
storage_path = Path(os.getenv('RAYFLOW_STORAGE_DIR') or str(BASE_DIR / 'storage')).expanduser()
STORAGE_ROOT = (storage_path if storage_path.is_absolute() else BASE_DIR / storage_path).resolve()
from app.editor.context import WorkspacePath
STORAGE_DIR = WorkspacePath(STORAGE_ROOT)
if ENVIRONMENT == 'production' and not os.getenv('RAYFLOW_STORAGE_DIR'):
    raise ValueError('Set RAYFLOW_STORAGE_DIR to a persistent mounted directory in production.')
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

CORS_ORIGINS = [] if ENVIRONMENT == 'production' else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ORIGINS += [origin.strip() for origin in os.environ.get('CORS_ORIGINS', '').split(',') if origin.strip()]
from urllib.parse import urlparse
for origin in CORS_ORIGINS:
    parsed = urlparse(origin)
    try:
        parsed.port
    except ValueError:
        raise ValueError('CORS_ORIGINS contains an invalid port.') from None
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('CORS_ORIGINS must contain HTTP(S) origins without paths, credentials, or wildcards.')
