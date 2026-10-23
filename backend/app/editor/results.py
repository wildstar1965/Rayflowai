"""Persist generated provider media before a job can report success."""
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import requests
from .providers import validate_url, credential
from .store import store

CDN_HOSTS = {
    'replicate': ('replicate.delivery',), 'fal': ('fal.media', 'fal.run'),
    'gemini': ('storage.googleapis.com', 'generativelanguage.googleapis.com'),
    'xai': ('imgen.x.ai', 'vidgen.x.ai'), 'elevenlabs': ('storage.googleapis.com',),
    'sonauto': ('sonauto.ai',), 'sonilo': ('sonilo.com',), 'ltx': ('ltx.video',),
    'runway': ('runwayml.com',), 'worldlabs': ('worldlabs.ai',),
    'higgsfield': ('higgsfield.ai',), 'machgen': ('machgen.ai',),
}
OUTPUT_KEYS = {'output', 'outputs', 'result', 'results', 'image', 'images', 'video', 'videos', 'audio',
               'audios', 'song_paths', 'artifacts', 'generatedSamples', 'generatedImages', 'generatedVideos',
               'video_url', 'image_url', 'audio_url', 'download_url', 'output_url', 'assets', 'task_output'}


def persist_binary(workspace, job_id, content, content_type, suffix=''):
    ext = mimetypes.guess_extension(content_type.split(';')[0]) or suffix or '.bin'
    digest = hashlib.sha256(content).hexdigest()
    identity = hashlib.sha256((job_id + digest).encode()).hexdigest()
    relative = f'generated/{identity}{ext}'
    store.put_blob(workspace, relative, content, content_type)
    url = '/api/editor/assets/file/' + relative
    store.put('assets', identity, workspace, {'name': f'Generated {identity[:8]}{ext}', 'path': relative,
              'url': url, 'type': content_type.split('/')[0], 'size': len(content), 'job_id': job_id, 'pending': False})
    return relative, url


def download_output(provider, url):
    configured = os.getenv('EDITOR_' + provider.upper().replace('-', '_') + '_OUTPUT_HOSTS', '')
    hosts = CDN_HOSTS.get(provider, ()) + tuple(part.strip() for part in configured.split(',') if part.strip())
    limit = int(os.getenv('EDITOR_OUTPUT_MAX_MB', '256')) * 1024**2
    for _ in range(4):
        hostname = urlparse(url).hostname or ''
        if not any(hostname == host or hostname.endswith('.' + host) for host in hosts):
            raise ValueError(f'The {provider} output host is not configured. Ask the backend operator to allow its media domain, then retry saving this job.')
        validate_url(url, [hostname])
        # Google video downloads require the judge's key. Never forward it to a CDN
        # or across a redirect to another host.
        headers = {'x-goog-api-key': credential('gemini')} if provider == 'gemini' and hostname == 'generativelanguage.googleapis.com' else {}
        with requests.get(url, headers=headers, stream=True, timeout=(10, 120), allow_redirects=False) as response:
            if 300 <= response.status_code < 400:
                url = urljoin(url, response.headers.get('location', ''))
                continue
            if response.status_code != 200:
                raise ValueError('Generated media could not be saved. Retry this job to save its existing provider result.')
            if int(response.headers.get('content-length', 0)) > limit:
                raise ValueError('Generated media exceeds the configured output size limit.')
            content = bytearray()
            for part in response.iter_content(1024 * 1024):
                content.extend(part)
                if len(content) > limit:
                    raise ValueError('Generated media exceeds the configured output size limit.')
            return bytes(content), response.headers.get('content-type', 'application/octet-stream')
    raise ValueError('Generated media exceeded the allowed redirect count.')


def persist_result(result, provider, workspace, job_id):
    result = dict(result)
    if result.get('base64'):
        relative, _ = persist_binary(workspace, job_id, base64.b64decode(result.pop('base64'), validate=True),
                                     result.get('content_type', 'application/octet-stream'))
        result['asset_path'] = relative
        return result
    if provider not in CDN_HOSTS:
        return result
    encoded = 'text' in result and 'json' in result.get('content_type', '')
    try:
        document = json.loads(result['text']) if encoded else result
    except ValueError:
        return result
    replacements = {}
    def visit(value, output=False):
        if isinstance(value, dict):
            binary = value.get('imageBytes') or (value.get('data') if value.get('mimeType', '').startswith(('image/', 'audio/', 'video/')) else None)
            if isinstance(binary, str):
                _, url = persist_binary(workspace, job_id, base64.b64decode(binary, validate=True), value.get('mimeType', 'image/png'))
                value = {**value, 'rayflowAssetUrl': url}
            # Polling and request URLs must remain provider endpoints.
            return {key: visit(child, (output or key in OUTPUT_KEYS) and key not in ('urls', 'status_url', 'response_url', 'cancel_url'))
                    for key, child in value.items()}
        if isinstance(value, list):
            return [visit(child, output) for child in value]
        if output and isinstance(value, str) and value.startswith('https://'):
            if value not in replacements:
                content, kind = download_output(provider, value)
                _, replacements[value] = persist_binary(workspace, job_id, content, kind, PurePosixPath(urlparse(value).path).suffix)
            return replacements[value]
        return value
    document = visit(document)
    if encoded:
        result['text'] = json.dumps(document)
        return result
    return document


def provider_receipt(result, provider):
    try:
        document = json.loads(result['text']) if 'text' in result else result
    except (TypeError, ValueError):
        return {}
    if not isinstance(document, dict):
        return {}
    identity = document.get('request_id') or document.get('id') or document.get('task_id') or document.get('name')
    urls = document.get('urls')
    poll = document.get('status_url') or (urls.get('get') if isinstance(urls, dict) else None)
    if identity and provider == 'replicate':
        poll = 'https://api.replicate.com/v1/predictions/' + str(identity)
    if identity and provider == 'runway':
        poll = 'https://api.dev.runwayml.com/v1/tasks/' + str(identity)
    if identity and provider == 'gemini' and 'operations/' in str(identity):
        poll = 'https://generativelanguage.googleapis.com/v1beta/' + str(identity)
    if identity and provider == 'xai':
        poll = 'https://api.x.ai/v1/videos/' + str(identity)
    if identity and provider == 'sonilo':
        poll = 'https://api.sonilo.com/v1/tasks/' + str(identity)
    if identity and provider == 'machgen':
        poll = 'https://api.machgen.ai/api/v0/tasks/' + str(identity)
    return {'provider': provider, 'provider_id': str(identity)[:400] if identity else None,
            'poll_url': poll, 'provider_status': document.get('status') or ('completed' if document.get('done') else None), 'response_url': document.get('response_url')}
