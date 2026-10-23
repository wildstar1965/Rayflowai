"""Optional cloud OAuth; access and refresh credentials stay in the backend vault."""
import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

import requests
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from .context import owner
from .providers import validate_url
from .security import encrypt, decrypt
from .store import store

router = APIRouter(prefix='/api/editor/cloud', tags=['cloud-integrations'])
PROVIDERS = {
    'dropbox': ('DROPBOX', 'https://www.dropbox.com/oauth2/authorize', 'https://api.dropboxapi.com/oauth2/token', ('api.dropboxapi.com', 'content.dropboxapi.com')),
    'google-drive': ('GOOGLE_DRIVE', 'https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token', ('www.googleapis.com', 'content.googleapis.com')),
}


def config(provider):
    if provider not in PROVIDERS:
        raise ValueError('Unsupported cloud provider.')
    item = PROVIDERS[provider]
    client = os.getenv(item[0] + '_CLIENT_ID', '')
    if not client:
        raise ValueError('This cloud integration needs an OAuth client configured by the backend operator.')
    return item, client


def auth_record(provider):
    return store.get('cloud_credentials', owner() + ':' + provider, owner())


@router.get('')
def connections():
    return {'providers': [{'id': provider, 'configured': bool(os.getenv(item[0] + '_CLIENT_ID')),
                           'connected': bool(auth_record(provider))} for provider, item in PROVIDERS.items()]}


@router.post('/{provider}/start')
def start(provider: str, request: Request):
    item, client = config(provider)
    origin = os.getenv('RAYFLOW_FRONTEND_URL') or str(request.base_url).rstrip('/')
    parsed = urlparse(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('Configure the public frontend URL before connecting cloud storage.')
    redirect = origin.rstrip('/') + '/api/editor/cloud/callback'
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode()).hexdigest()
    store.put('oauth_states', digest, owner(), {'provider': provider, 'expires': time.time() + 600,
              'redirect': redirect, 'verifier': encrypt(verifier, owner(), 'oauth:' + digest)})
    params = {'response_type': 'code', 'client_id': client, 'redirect_uri': redirect, 'state': state,
              'code_challenge_method': 'S256', 'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
    if provider == 'dropbox':
        params['token_access_type'] = 'offline'
    else:
        params.update(scope='https://www.googleapis.com/auth/drive.file', access_type='offline', prompt='consent')
    return {'url': item[1] + '?' + urlencode(params)}


def token_request(provider, body):
    item, client = config(provider)
    body = {**body, 'client_id': client}
    secret = os.getenv(item[0] + '_CLIENT_SECRET')
    if secret:
        body['client_secret'] = secret
    try:
        response = requests.post(item[2], data=body, timeout=(10, 30), allow_redirects=False)
    except requests.RequestException:
        raise ValueError('The cloud authorization service could not be reached.') from None
    if response.status_code != 200:
        raise ValueError('Cloud authorization failed. Reconnect the account in Connections.')
    value = response.json()
    if not value.get('access_token'):
        raise ValueError('Cloud authorization returned no access token.')
    return value


def save_auth(provider, value):
    value['expires_at'] = time.time() + int(value.get('expires_in', 3600))
    store.put('cloud_credentials', owner() + ':' + provider, owner(),
              {'encrypted': encrypt(json.dumps(value), owner(), 'cloud:' + provider)})


@router.get('/callback')
def callback(state: str = '', code: str = ''):
    if not state or not code or len(state) > 200 or len(code) > 4096:
        raise ValueError('Cloud authorization was cancelled or the response is invalid.')
    digest = hashlib.sha256(state.encode()).hexdigest()
    record = store.take('oauth_states', digest, owner())
    if not record or record['expires'] < time.time():
        raise ValueError('Cloud authorization expired. Connect again from the original browser.')
    value = token_request(record['provider'], {'grant_type': 'authorization_code', 'code': code,
                 'redirect_uri': record['redirect'], 'code_verifier': decrypt(record['verifier'], owner(), 'oauth:' + digest)})
    save_auth(record['provider'], value)
    return RedirectResponse('/#/connections', status_code=303)


@router.delete('/{provider}')
def disconnect(provider: str):
    if provider not in PROVIDERS:
        raise ValueError('Unsupported cloud provider.')
    store.delete('cloud_credentials', owner() + ':' + provider, owner())
    return {'ok': True}


def access_token(provider):
    with store.lock:
        record = auth_record(provider)
        if not record:
            raise ValueError('Connect this cloud account in Connections.')
        value = json.loads(decrypt(record['encrypted'], owner(), 'cloud:' + provider))
        if value.get('expires_at', 0) < time.time() + 60:
            if not value.get('refresh_token'):
                raise ValueError('Cloud authorization expired. Reconnect in Connections.')
            refreshed = token_request(provider, {'grant_type': 'refresh_token', 'refresh_token': value['refresh_token']})
            value.update(refreshed)
            save_auth(provider, value)
        return value['access_token']


def cloud_request(provider, url, method='GET', headers=None, body=None, body_base64=None, **ignored):
    item, _ = config(provider)
    parsed = validate_url(url, item[3])
    if method not in ('GET', 'POST', 'PATCH', 'PUT', 'DELETE') or (provider == 'dropbox' and not parsed.path.startswith('/2/')):
        raise ValueError('Unsupported cloud operation.')
    key = access_token(provider)
    clean_headers = {name: value for name, value in (headers or {}).items() if name.lower() in ('content-type', 'dropbox-api-arg', 'accept')}
    clean_headers['Authorization'] = 'Bearer ' + key
    response = requests.request(method, url, headers=clean_headers, data=base64.b64decode(body_base64, validate=True) if body_base64 else body,
                                timeout=(10, 120), allow_redirects=False)
    if 300 <= response.status_code < 400:
        raise ValueError('Cloud redirects are not allowed.')
    kind = response.headers.get('content-type', 'application/octet-stream')
    result = {'status': response.status_code, 'content_type': kind, 'headers': {name: value for name, value in response.headers.items() if name.lower() == 'dropbox-api-result'}}
    if 'json' in kind or kind.startswith('text/'):
        result['text'] = response.text.replace(key, '[redacted]')
    else:
        result['base64'] = base64.b64encode(response.content).decode()
    return result
