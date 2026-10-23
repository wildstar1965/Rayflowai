"""Optional Supabase email-code sign-in, with backend-only token storage."""
import hashlib
import json
import os
import re
import secrets
import time
import uuid

import requests
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from .context import owner, account
from .security import COOKIE, SESSION_SECONDS, resolve_session, set_cookie, encrypt, end_session, create_session
from .store import store

router = APIRouter(prefix='/api/editor/account', tags=['optional-accounts'])


def require_account():
    value = account.get()
    if not value:
        raise HTTPException(401, 'Sign in to use teams or restore an account workspace.')
    return value


def rate_limit(name, seconds=30):
    with store.lock:
        previous = store.get('auth_limits', owner() + ':' + name, owner())
        if previous and previous['after'] > time.time():
            raise HTTPException(429, 'Wait before trying again.')
        store.put('auth_limits', owner() + ':' + name, owner(), {'after': time.time() + seconds})


def auth_request(path, payload):
    if not store.cloud:
        raise ValueError('Accounts require the backend Supabase configuration. Guest editing remains available.')
    response = requests.post(os.environ['SUPABASE_URL'].rstrip('/') + '/auth/v1/' + path,
                             headers={'apikey': os.environ['SUPABASE_SERVICE_ROLE_KEY']}, json=payload,
                             timeout=(10, 30), allow_redirects=False)
    if response.status_code >= 300:
        raise ValueError('Sign-in could not be completed. Check the email and code, then try again.')
    return response.json()


@router.get('')
def status():
    user = account.get()
    workspaces = store.list('account_workspaces', user['id']) if user else []
    return {'configured': store.cloud, 'user': user, 'workspace_id': owner(), 'workspaces': workspaces}


@router.post('/code')
def send_code(payload: dict):
    email = str(payload.get('email', '')).strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254:
        raise ValueError('Enter a valid email address.')
    rate_limit('code', 60)
    auth_request('otp', {'email': email, 'create_user': True})
    return {'ok': True, 'message': 'If sign-in is available, a code has been sent. Enter the code from your email.'}


@router.post('/verify')
def verify_code(payload: dict, request: Request):
    rate_limit('verify', 2)
    email, code = str(payload.get('email', '')).strip().lower(), str(payload.get('code', '')).strip()
    if not re.fullmatch(r'\d{6,10}', code) or len(email) > 254:
        raise ValueError('Enter the email verification code.')
    result = auth_request('verify', {'email': email, 'token': code, 'type': 'email'})
    user = result.get('user') or {}
    if not user.get('id') or not user.get('email_confirmed_at') or not result.get('access_token'):
        raise ValueError('The account email has not been verified.')
    current = resolve_session(request.cookies.get(COOKIE))
    identity = owner()
    if current.get('account') and current['account']['id'] != user['id']:
        identity = str(uuid.uuid4())
    public = {'id': user['id'], 'email': user.get('email', email),
              'name': user.get('user_metadata', {}).get('name') or email.split('@')[0]}
    store.put('account_workspaces', user['id'] + ':' + identity, user['id'],
              {'workspace_id': identity, 'name': 'Workspace ' + identity[:8], 'created': time.time()})
    token = secrets.token_urlsafe(40)
    digest = hashlib.sha256(token.encode()).hexdigest()
    store.put('sessions', digest, 'system', {'workspace_id': identity, 'account': public, 'created': time.time(),
              'expires': time.time() + SESSION_SECONDS})
    store.put('account_credentials', digest, user['id'], {'encrypted': encrypt(json.dumps({
        'access_token': result['access_token'], 'refresh_token': result.get('refresh_token')}), user['id'], 'auth:' + digest)})
    end_session(request.cookies.get(COOKIE))
    response = JSONResponse({'user': public, 'workspace_id': identity})
    set_cookie(response, token)
    return response


@router.post('/workspace')
def switch_workspace(payload: dict, request: Request):
    user = require_account()
    identity = str(payload.get('workspace_id', ''))
    if not store.get('account_workspaces', user['id'] + ':' + identity, user['id']):
        raise HTTPException(404, 'Account workspace not found.')
    digest = hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()
    record = store.get('sessions', digest, 'system')
    record['workspace_id'] = identity
    store.put('sessions', digest, 'system', record, expected=record['revision'])
    return {'workspace_id': identity}


@router.post('/logout')
def logout(request: Request):
    user = account.get()
    token = request.cookies.get(COOKIE)
    if user and token:
        store.delete('account_credentials', hashlib.sha256(token.encode()).hexdigest(), user['id'])
    end_session(token)
    token, _ = create_session()
    response = JSONResponse({'ok': True})
    set_cookie(response, token)
    return response
