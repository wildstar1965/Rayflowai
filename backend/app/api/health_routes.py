"""Readiness checks for required processing infrastructure, not optional AI."""
import sqlite3
import subprocess
import tempfile
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.core.config import STORAGE_DIR, FFMPEG_PATH, FFPROBE_PATH
from app.services.job_history import database

router = APIRouter(prefix='/api', tags=['health'])


@router.get('/ready')
def readiness():
    checks = {}
    try:
        with tempfile.TemporaryFile(dir=STORAGE_DIR) as stream:
            stream.write(b'ready')
            stream.flush()
        with database() as connection:
            connection.execute('SELECT 1').fetchone()
        checks['storage'] = True
    except (OSError, sqlite3.Error):
        checks['storage'] = False
    for name, executable in [('ffmpeg', FFMPEG_PATH), ('ffprobe', FFPROBE_PATH)]:
        try:
            result = subprocess.run([executable, '-version'], capture_output=True, timeout=5)
            checks[name] = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            checks[name] = False
    if os.getenv('RAYFLOW_ENV') == 'production':
        from app.editor.store import store
        from app.editor.security import vault_key
        try:
            vault_key()
            checks['vault'] = True
        except Exception:
            checks['vault'] = False
        try:
            if not store.cloud:
                raise RuntimeError('Storage is not configured')
            store.request('GET', '/rest/v1/rayflow_records', params={'select': 'id', 'limit': '1'})
            checks['supabase'] = True
        except Exception:
            checks['supabase'] = False
        runtime = Path(__file__).resolve().parents[2] / 'editor-runtime' / 'node_modules'
        checks['editor_runtime'] = (runtime / '@google/genai/package.json').is_file() and (runtime / 'fluent-ffmpeg/package.json').is_file()
    ready = all(checks.values())
    return JSONResponse({'status': 'ready' if ready else 'unavailable', 'checks': checks}, status_code=200 if ready else 503)
