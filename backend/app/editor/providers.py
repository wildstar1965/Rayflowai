"""The provider catalog is public; credentials and authenticated transport are not."""
import base64
import ipaddress
import os
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from .context import owner
from .security import encrypt, decrypt
from .store import store

PROVIDERS = {
    'notebooklm': ('NotebookLM MCP', [], 'Authorization', 'Bearer ', None),
    'gemini': ('Google Gemini', ['generativelanguage.googleapis.com'], 'x-goog-api-key', '', '/v1beta/models'),
    'replicate': ('Replicate', ['api.replicate.com'], 'Authorization', 'Bearer ', '/v1/account'),
    'fal': ('fal.ai', ['fal.run', 'queue.fal.run', 'rest.alpha.fal.ai'], 'Authorization', 'Key ', None),
    'xai': ('xAI', ['api.x.ai'], 'Authorization', 'Bearer ', '/v1/models'),
    'elevenlabs': ('ElevenLabs', ['api.elevenlabs.io'], 'xi-api-key', '', '/v1/voices'),
    'sonauto': ('Sonauto', ['api.sonauto.ai'], 'Authorization', 'Bearer ', None),
    'sonilo': ('Sonilo', ['api.sonilo.com'], 'Authorization', 'Bearer ', None),
    'ltx': ('LTX', ['api.ltx.video'], 'Authorization', 'Bearer ', None),
    'runway': ('Runway', ['api.dev.runwayml.com'], 'Authorization', 'Bearer ', '/v1/organization'),
    'worldlabs': ('World Labs', ['api.worldlabs.ai'], 'WLT-Api-Key', '', None),
    'higgsfield': ('Higgsfield', ['api.higgsfield.ai'], 'Authorization', 'Key ', None),
    'machgen': ('MachGen', ['api.machgen.ai'], 'Authorization', 'Bearer ', None),
    'brave_search': ('Brave Search', ['api.search.brave.com'], 'X-Subscription-Token', '', '/res/v1/web/search?q=Rayflow&count=1'),
    'unsplash': ('Unsplash', ['api.unsplash.com'], 'Authorization', 'Client-ID ', '/photos?per_page=1'),
    'sketchfab': ('Sketchfab', ['api.sketchfab.com'], 'Authorization', 'Token ', '/v3/me'),
    'openrouter': ('OpenRouter', ['openrouter.ai'], 'Authorization', 'Bearer ', '/api/v1/key'),
    'pixabay': ('Pixabay', ['pixabay.com'], '', '', '/api/?q=nature&per_page=3'),
}
LOCAL_PROVIDERS = {'ollama': 'http://127.0.0.1:11434', 'lmstudio': 'http://127.0.0.1:1234',
                   'openai-compatible': 'http://127.0.0.1:8080', 'comfyui': 'http://127.0.0.1:8188',
                   'draw-things': 'http://127.0.0.1:7860'}


def provider_record(provider, identity=None):
    identity = identity or owner()
    return store.get('credentials', identity + ':' + provider, identity)


def credential(provider, identity=None):
    identity = identity or owner()
    record = provider_record(provider, identity)
    return decrypt(record['encrypted'], identity, provider) if record and record.get('encrypted') else ''


def public_providers():
    rows = []
    for identity, metadata in PROVIDERS.items():
        record = provider_record(identity) or {}
        rows.append({'id': identity, 'label': metadata[0], 'configured': bool(record.get('encrypted')),
                     'model': record.get('model', ''), 'tested': record.get('tested', False),
                     'can_test': bool(metadata[4]), 'hosts': metadata[1]})
    for identity, default in LOCAL_PROVIDERS.items():
        record = provider_record(identity) or {}
        configured = os.getenv('EDITOR_' + identity.upper().replace('-', '_') + '_URL', '')
        rows.append({'id': identity, 'label': identity, 'configured': bool(configured),
                     'model': record.get('model', ''), 'base_url': configured,
                     'local': True, 'can_test': True, 'tested': record.get('tested', False), 'hosts': []})
    return rows


def save_provider(provider, key=None, model=None):
    if provider not in PROVIDERS and provider not in LOCAL_PROVIDERS:
        raise ValueError('Unknown provider.')
    identity = owner()
    previous = provider_record(provider) or {}
    if key is not None and key.strip():
        if provider in LOCAL_PROVIDERS:
            raise ValueError('Local service addresses are configured by the backend operator.')
        if len(key) > 4096 or any(character in key for character in '\r\n\x00'):
            raise ValueError('Enter a single-line provider key of at most 4096 characters.')
        if provider == 'higgsfield' and ':' not in key:
            raise ValueError('Higgsfield requires KEY_ID:KEY_SECRET.')
        previous['encrypted'] = encrypt(key.strip(), identity, provider)
        previous['tested'] = False
    if model is not None:
        if not isinstance(model, str) or len(model) > 200 or any(character in model for character in '\r\n\x00'):
            raise ValueError('Invalid model identifier.')
        previous['model'] = model.strip()
    store.put('credentials', identity + ':' + provider, identity, previous)


def delete_provider(provider):
    identity = owner()
    store.delete('credentials', identity + ':' + provider, identity)


def validate_url(url, allowed_hosts=None, local=False):
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.scheme not in (('http', 'https') if local else ('https',)):
        raise ValueError('Unsupported provider URL.')
    if not parsed.hostname or (allowed_hosts is not None and parsed.hostname not in allowed_hosts):
        raise ValueError('This provider endpoint is not allowed.')
    if not local:
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except OSError:
            raise ValueError('The provider hostname could not be resolved.') from None
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise ValueError('Private network destinations are not allowed.')
    return parsed


def proxy_request(provider, url, method='GET', headers=None, body=None, body_base64=None, form=None):
    if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
        raise ValueError('Unsupported provider method.')
    metadata = PROVIDERS.get(provider)
    local_base = os.getenv('EDITOR_' + provider.upper().replace('-', '_') + '_URL', '') if provider in LOCAL_PROVIDERS else ''
    if not metadata and not local_base:
        raise ValueError('This service is not configured on the backend.')
    if local_base:
        requested = urlparse(url)
        base = urlparse(local_base)
        if provider == 'comfyui':
            from .comfy import prepare
            body, form = prepare(requested.path, requested.query, method, body, form)
            body_base64 = None
        # Browser defaults select the service, never the remote network target.
        url = urlunparse((base.scheme, base.netloc, base.path.rstrip('/') + requested.path, '', requested.query, ''))
        if provider == 'ollama' and requested.path not in ('/api/tags', '/api/version', '/api/ps', '/api/show', '/api/chat', '/api/generate', '/api/embed', '/api/embeddings', '/v1/models', '/v1/chat/completions', '/v1/completions', '/v1/embeddings'):
            raise ValueError('Installing or removing server models requires backend operator access.')
        if provider in ('lmstudio', 'openai-compatible') and not requested.path.startswith(('/v1/models', '/v1/chat/completions', '/v1/completions', '/v1/embeddings', '/v1/responses')):
            raise ValueError('Only model discovery and inference are available to hosted guests.')
        validate_url(url, [base.hostname], local=True)
        key = ''
    else:
        validate_url(url, metadata[1])
        key = credential(provider)
        if not key:
            raise ValueError(f'Add your {metadata[0]} key in Connections to use this feature.')
    clean_headers = {name: value for name, value in (headers or {}).items()
                     if name.lower() in ('content-type', 'accept', 'prefer', 'x-runway-version', 'range',
                                         'x-goog-upload-protocol', 'x-goog-upload-command', 'x-goog-upload-offset',
                                         'x-goog-upload-header-content-length', 'x-goog-upload-header-content-type')}
    parsed = urlparse(url)
    query = [(name, value) for name, value in parse_qsl(parsed.query, keep_blank_values=True)
             if name.lower() not in ('key', 'api_key', 'token', 'access_token', 'client_id')]
    if provider == 'pixabay':
        query.append(('key', key))
    url = urlunparse(parsed._replace(query=urlencode(query)))
    if metadata and metadata[2]:
        clean_headers[metadata[2]] = metadata[3] + key
    if provider == 'runway':
        clean_headers.setdefault('X-Runway-Version', '2024-11-06')
    data = base64.b64decode(body_base64, validate=True) if body_base64 else body
    files = None
    if form is not None:
        clean_headers = {name: value for name, value in clean_headers.items() if name.lower() != 'content-type'}
        files = []
        for entry in form:
            if 'base64' in entry:
                files.append((entry['name'], (entry.get('filename', 'upload'), base64.b64decode(entry['base64'], validate=True), entry.get('type', 'application/octet-stream'))))
            else:
                files.append((entry['name'], (None, str(entry.get('value', '')))))
        data = None
    try:
        response = requests.request(method, url, headers=clean_headers, data=data, files=files, timeout=(10, 600), allow_redirects=False)
    except requests.Timeout:
        return {'status': 504, 'content_type': 'application/json', 'text': '{"error":"Provider request timed out."}'}
    except requests.RequestException:
        return {'status': 502, 'content_type': 'application/json', 'text': '{"error":"Provider request failed. Check connectivity and retry."}'}
    if 300 <= response.status_code < 400:
        return {'status': 502, 'content_type': 'application/json', 'text': '{"error":"Unexpected provider redirect was blocked."}'}
    content_type = response.headers.get('content-type', 'application/octet-stream')
    result = {'status': response.status_code, 'content_type': content_type,
              'headers': {name: value for name, value in response.headers.items()
                          if name.lower() in ('x-goog-upload-url', 'x-goog-upload-status', 'retry-after')}}
    if 'json' in content_type or content_type.startswith('text/'):
        text = response.text
        if key:
            text = text.replace(key, '[redacted]')
        result['text'] = text
    else:
        result['base64'] = base64.b64encode(response.content).decode()
    if provider == 'comfyui':
        from .comfy import record
        record(requested.path, method, result)
    return result


def test_provider(provider):
    if provider in LOCAL_PROVIDERS:
        path = '/api/tags' if provider == 'ollama' else '/system_stats' if provider == 'comfyui' else '/v1/models'
        result = proxy_request(provider, LOCAL_PROVIDERS[provider] + path)
    else:
        metadata = PROVIDERS.get(provider)
        if not metadata:
            raise ValueError('Unknown provider.')
        if not metadata[4]:
            return {'ok': bool(credential(provider)), 'verified': False, 'message': 'Key saved. This provider has no configured non-generating verification endpoint; model access is checked when you run a request.'}
        result = proxy_request(provider, 'https://' + metadata[1][0] + metadata[4])
    valid = 200 <= result['status'] < 300
    record = provider_record(provider) or {}
    record['tested'] = valid
    store.put('credentials', owner() + ':' + provider, owner(), record)
    return {'ok': valid, 'verified': valid, 'message': 'Connection verified.' if valid else f'Provider returned HTTP {result["status"]}. Check the key and account access.'}
