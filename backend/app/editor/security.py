"""Guest sessions and authenticated encryption; no browser-readable secrets."""
import base64
import hashlib
import os
import secrets
import time
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request
from .context import owner
from .store import root_path, store, StorageUnavailable

COOKIE = 'rayflow_session'
SESSION_SECONDS = 7 * 24 * 3600


def vault_key():
    secret = os.getenv('RAYFLOW_VAULT_SECRET')
    if secret:
        if len(secret) < 32:
            raise StorageUnavailable('RAYFLOW_VAULT_SECRET must contain at least 32 characters.')
        return hashlib.sha256(secret.encode()).digest()
    if os.getenv('RAYFLOW_ENV') == 'production':
        raise StorageUnavailable('Configure RAYFLOW_VAULT_SECRET on the backend before saving keys.')
    path = root_path() / 'private' / 'vault.key'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
    return path.read_bytes()


def encrypt(value, identity, name):
    nonce = secrets.token_bytes(12)
    data = AESGCM(vault_key()).encrypt(nonce, value.encode(), f'{identity}:{name}'.encode())
    return base64.urlsafe_b64encode(nonce + data).decode()


def decrypt(value, identity, name):
    data = base64.urlsafe_b64decode(value)
    return AESGCM(vault_key()).decrypt(data[:12], data[12:], f'{identity}:{name}'.encode()).decode()


def create_session():
    token = secrets.token_urlsafe(40)
    digest = hashlib.sha256(token.encode()).hexdigest()
    identity = str(uuid.uuid4())
    record = {'workspace_id': identity, 'expires': time.time() + SESSION_SECONDS, 'created': time.time()}
    store.put('sessions', digest, 'system', record)
    return token, record


def resolve_session(token):
    if not token or len(token) > 256:
        return None
    record = store.get('sessions', hashlib.sha256(token.encode()).hexdigest(), 'system')
    return record if record and record['expires'] > time.time() else None


def end_session(token):
    if token:
        store.delete('sessions', hashlib.sha256(token.encode()).hexdigest(), 'system')


def require_origin(request: Request):
    origin = request.headers.get('origin')
    if not origin:
        return
    from app.core.config import CORS_ORIGINS
    allowed = set(CORS_ORIGINS)
    allowed.update(value.strip().rstrip('/') for value in os.getenv('RAYFLOW_PUBLIC_ORIGINS', '').split(',') if value.strip())
    allowed.add(str(request.base_url).rstrip('/'))
    if origin not in allowed:
        raise HTTPException(403, 'This origin cannot change the workspace.')


def set_cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=os.getenv('RAYFLOW_ENV') == 'production', samesite='lax', path='/')


def session_public():
    from .context import account
    identity = owner()
    prefs = store.get('preferences', identity, identity) or {}
    return {'workspace_id': identity, 'guest': account.get() is None, 'account': account.get(),
            'preferences': prefs, 'storage': 'supabase' if store.cloud else 'local'}
