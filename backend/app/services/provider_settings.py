"""Write-only local provider configuration. Never return or log saved credentials."""
import json
import os
import threading
import uuid
from urllib.parse import urlparse

import requests
from app.core.config import STORAGE_DIR

SETTINGS_PATH = STORAGE_DIR / 'private' / 'providers.json'
_lock = threading.RLock()
FIELDS = {
    'OPENROUTER_API_KEY', 'OPENROUTER_MODEL', 'PIXABAY_API_KEY',
    'OLLAMA_HOST', 'OLLAMA_MODEL', 'AI_PROVIDER',
}


def _read():
    if not SETTINGS_PATH.exists():
        return {}
    try:
        value = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise ValueError('Provider settings cannot be read. Restore the private settings file or check its permissions.') from None


def setting(key, default=''):
    from app.editor.context import workspace_id
    if workspace_id.get():
        from app.editor.providers import credential, provider_record
        from app.editor.store import store
        provider = {'OPENROUTER_API_KEY': 'openrouter', 'PIXABAY_API_KEY': 'pixabay'}.get(key)
        if provider:
            return credential(provider)
        prefs = store.get('preferences', workspace_id.get(), workspace_id.get()) or {}
        values = prefs.get('rayflow', {})
        if key == 'OPENROUTER_MODEL':
            return (provider_record('openrouter') or {}).get('model') or default
        if key == 'OLLAMA_HOST':
            return os.getenv('EDITOR_OLLAMA_URL') or os.getenv('OLLAMA_HOST', default)
        return values.get(key, default)
    with _lock:
        # Production configuration must not inherit a developer's private file.
        if os.getenv('RAYFLOW_ENV', 'development') == 'production':
            return os.getenv(key, default)
        return _read().get(key, os.getenv(key, default))


def validate_host(value):
    target = value.strip().rstrip('/')
    parsed = urlparse(target)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError('Use an HTTP(S) Ollama base URL without credentials, a path, or query parameters.')
    try:
        parsed.port
    except ValueError:
        raise ValueError('Ollama port must be a valid port number.') from None
    # Remote hosts are selected by the server operator, never arbitrary browser input.
    allowed = {os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')}
    allowed.update(x.strip().rstrip('/') for x in os.getenv('OLLAMA_ALLOWED_HOSTS', '').split(',') if x.strip())
    if parsed.hostname not in ('localhost', '127.0.0.1', '::1') and target not in allowed:
        raise ValueError('This remote Ollama host is not allowed. Add it to OLLAMA_ALLOWED_HOSTS on the backend.')
    return target


def save_settings(patch):
    from app.editor.context import workspace_id
    if workspace_id.get():
        from app.editor.providers import save_provider
        from app.editor.store import store
        if set(patch) - FIELDS:
            raise ValueError('Unsupported provider setting.')
        identity = workspace_id.get()
        prefs = store.get('preferences', identity, identity) or {}
        values = prefs.setdefault('rayflow', {})
        for key, value in patch.items():
            if not isinstance(value, str) or len(value) > 4096 or '\n' in value or '\r' in value:
                raise ValueError('Invalid configuration value.')
            if key in ('OPENROUTER_API_KEY', 'PIXABAY_API_KEY'):
                if value.strip():
                    save_provider('openrouter' if key == 'OPENROUTER_API_KEY' else 'pixabay', key=value)
            elif key == 'OPENROUTER_MODEL':
                save_provider('openrouter', model=value)
            elif key == 'OLLAMA_HOST':
                if value != setting(key):
                    raise ValueError('The backend operator configures local model server addresses.')
            elif key == 'AI_PROVIDER' and value not in ('auto', 'ollama', 'openrouter', 'local'):
                raise ValueError('Unsupported AI provider.')
            else:
                values[key] = value
        store.put('preferences', identity, identity, prefs)
        return
    if set(patch) - FIELDS:
        raise ValueError('Unsupported provider setting.')
    clean = {}
    for key, value in patch.items():
        if not isinstance(value, str) or len(value) > 4096 or '\n' in value or '\r' in value:
            raise ValueError('Settings must be single-line strings of at most 4096 characters.')
        value = value.strip()
        if key.endswith('_API_KEY') and not value:
            continue  # Empty password inputs preserve working credentials.
        if key == 'OLLAMA_HOST':
            value = validate_host(value)
        if key == 'AI_PROVIDER' and value not in ('auto', 'ollama', 'openrouter', 'local'):
            raise ValueError('Select Automatic, Ollama, OpenRouter, or local commands.')
        if key.endswith('_MODEL') and ((not value and key != 'OLLAMA_MODEL') or len(value) > 200 or any(c.isspace() for c in value)):
            raise ValueError('Enter a model ID without spaces (at most 200 characters).')
        clean[key] = value
    with _lock:
        current = _read()
        current.update(clean)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = SETTINGS_PATH.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(current, stream)
            temporary.replace(SETTINGS_PATH)
        finally:
            temporary.unlink(missing_ok=True)


def public_settings():
    return {
        'openrouter_configured': bool(setting('OPENROUTER_API_KEY')),
        'openrouter_model': setting('OPENROUTER_MODEL', 'openrouter/free'),
        'pixabay_configured': bool(setting('PIXABAY_API_KEY')),
        'ollama_host': setting('OLLAMA_HOST', 'http://127.0.0.1:11434'),
        'ollama_model': setting('OLLAMA_MODEL'),
        'ai_provider': setting('AI_PROVIDER', 'auto'),
        'editable': bool(__import__('app.editor.context', fromlist=['workspace_id']).workspace_id.get()) or os.getenv('RAYFLOW_ENV', 'development') != 'production',
    }


def test_provider(provider):
    if provider == 'ollama':
        from app.services.ollama_client import check_ollama_status
        status = check_ollama_status()
        return {'ok': status.ready, 'message': status.error or f'Ollama responded with {len(status.models)} installed models. Use Test selected model to verify inference.'}
    if provider not in ('openrouter', 'pixabay'):
        raise ValueError('Unsupported provider.')
    key = setting('OPENROUTER_API_KEY' if provider == 'openrouter' else 'PIXABAY_API_KEY')
    if not key:
        return {'ok': False, 'message': f'{provider.title()} has no backend API key configured.'}
    try:
        if provider == 'openrouter':
            response = requests.get('https://openrouter.ai/api/v1/key', headers={'Authorization': f'Bearer {key}'}, timeout=(4, 10), allow_redirects=False)
        else:
            response = requests.get('https://pixabay.com/api/', params={'key': key, 'q': 'nature', 'per_page': 3}, timeout=(4, 10), allow_redirects=False)
        if response.status_code in (400, 401, 403):
            return {'ok': False, 'message': 'Credentials were rejected or access is forbidden. Check the backend API key.'}
        if response.status_code == 429:
            return {'ok': False, 'message': 'The service rate limit was reached. Wait before retrying.'}
        if response.status_code != 200:
            return {'ok': False, 'message': f'The service returned HTTP {response.status_code}.'}
        data = response.json()
        if not isinstance(data, dict) or ('data' if provider == 'openrouter' else 'hits') not in data:
            return {'ok': False, 'message': 'The service returned an unexpected response.'}
        return {'ok': True, 'message': 'The service verified the saved credentials. Generation depends on model access and account limits.'}
    except requests.Timeout:
        return {'ok': False, 'message': 'Connection test timed out. Check network access and retry.'}
    except (requests.RequestException, ValueError):
        return {'ok': False, 'message': 'Could not verify the service. Check network access and retry.'}
