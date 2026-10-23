import asyncio
import hashlib
import json
import os
import secrets
import time
import threading
from urllib.parse import urlparse
from fastapi import APIRouter, Request, WebSocket
from app.editor.context import owner, workspace_id
from app.editor.providers import credential
from app.editor.store import store
from app.editor.runtime import RUNTIME, validate_sdk

router = APIRouter(tags=['editor-live'])
_live_lock = threading.Lock()
_live_workspaces = set()


@router.post('/api/editor/live-ticket')
def live_ticket(payload: dict, request: Request):
    validate_sdk(payload)
    if not isinstance(payload.get('config', {}), dict) or len(json.dumps(payload)) > 200_000:
        raise ValueError('Invalid live session configuration.')
    if not credential('gemini'):
        raise ValueError('Connect Google Gemini before starting live voice.')
    public = os.getenv('RENDER_EXTERNAL_URL') or os.getenv('EDITOR_BACKEND_PUBLIC_URL') or str(request.base_url).rstrip('/')
    parsed = urlparse(public)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('Configure the backend public URL for live voice.')
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    store.put('live_tickets', digest, 'system', {'workspace': owner(), 'expires': time.time() + 60,
              'model': str(payload.get('model', ''))[:200], 'config': payload.get('config', {})})
    return {'ticket': token, 'url': ('wss' if parsed.scheme == 'https' else 'ws') + '://' + parsed.netloc + '/api/editor/live'}


@router.websocket('/api/editor/live')
async def live(websocket: WebSocket):
    from app.core.config import CORS_ORIGINS
    allowed = set(CORS_ORIGINS) | {value.strip() for value in os.getenv('RAYFLOW_PUBLIC_ORIGINS', '').split(',') if value.strip()}
    origin = websocket.headers.get('origin')
    if origin and origin not in allowed:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    process = None
    context = None
    tasks = []
    live_workspace = None
    try:
        opening = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        ticket = opening.get('ticket', '')
        if not isinstance(ticket, str) or len(ticket) > 200:
            raise ValueError('Invalid live session ticket.')
        digest = hashlib.sha256(ticket.encode()).hexdigest()
        record = store.take('live_tickets', digest, 'system')
        if not record or record['expires'] < time.time():
            raise ValueError('Live session ticket expired. Reconnect.')
        with _live_lock:
            if record['workspace'] in _live_workspaces or len(_live_workspaces) >= int(os.getenv('EDITOR_LIVE_CONCURRENCY', '4')):
                raise ValueError('Live voice is at capacity. End the active session or retry shortly.')
            live_workspace = record['workspace']
            _live_workspaces.add(live_workspace)
        context = workspace_id.set(record['workspace'])
        key = credential('gemini')
        if not key:
            raise ValueError('Connect Google Gemini before starting live voice.')
        process = await asyncio.create_subprocess_exec('node', str(RUNTIME / 'live.mjs'),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        process.stdin.write((json.dumps({'credential': key, 'model': record['model'], 'config': record['config']}) + '\n').encode())
        await process.stdin.drain()
        async def receive():
            while True:
                message = await websocket.receive_text()
                if len(message) > 2_000_000:
                    raise ValueError('Voice message is too large.')
                value = json.loads(message)
                validate_sdk(value)
                if value.get('method') not in ('sendRealtimeInput', 'sendClientContent', 'sendToolResponse'):
                    raise ValueError('Unsupported live operation.')
                process.stdin.write((json.dumps(value) + '\n').encode())
                await process.stdin.drain()
        async def send():
            while line := await process.stdout.readline():
                await websocket.send_text(line.decode())
        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=1800)
    except Exception as exc:
        try:
            await websocket.send_json({'error': str(exc) if isinstance(exc, ValueError) else 'Live voice disconnected. Reconnect to continue.'})
        except Exception:
            pass
    finally:
        if live_workspace:
            with _live_lock:
                _live_workspaces.discard(live_workspace)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        if context is not None:
            workspace_id.reset(context)
        try:
            await websocket.close()
        except Exception:
            pass
