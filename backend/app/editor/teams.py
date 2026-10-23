"""Account membership, private team projects and durable collaboration events."""
import copy
import hashlib
import secrets
import time
import uuid

from fastapi import APIRouter, HTTPException
from .accounts import require_account
from .context import account, owner
from .store import store, Conflict

router = APIRouter(prefix='/api/editor/teams', tags=['optional-teams'])


def member(team_id, write=False):
    user = require_account()
    record = store.get('team_members', team_id + ':' + user['id'], user['id'])
    if not record or (write and record['role'] == 'viewer'):
        raise HTTPException(403, 'Team membership does not permit this operation.')
    return record


def project_owner(project_id, write=False):
    link = store.get('shared_project_access', project_id, 'system')
    if link:
        if not account.get():
            raise HTTPException(404, 'Project not found.')
        member(link['team_id'], write)
        return link['team_id']
    if store.get('projects', project_id, owner()):
        return owner()
    raise HTTPException(404, 'Project not found.')


def project_role(project_id):
    link = store.get('shared_project_access', project_id, 'system')
    return member(link['team_id'])['role'] if link else 'owner'


def shared_projects():
    user = account.get()
    if not user:
        return []
    return [project for membership in store.list('team_members', user['id'])
            for project in store.list('projects', membership['team_id'])]


@router.get('')
def list_teams():
    user = require_account()
    return {'teams': [{**store.get('teams', row['team_id'], row['team_id']), 'role': row['role']}
                      for row in store.list('team_members', user['id'])]}


@router.post('')
def create_team(payload: dict):
    user = require_account()
    identity = str(uuid.uuid4())
    name = str(payload.get('name', '')).strip()[:120]
    if not name:
        raise ValueError('Enter a team name.')
    result = store.put('teams', identity, identity, {'name': name, 'creator': user['id'], 'created': time.time()})
    store.put('team_members', identity + ':' + user['id'], user['id'], {'team_id': identity, 'role': 'owner', 'name': user['name']})
    return result


@router.post('/{team_id}/invite')
def invite(team_id: str, payload: dict):
    if member(team_id)['role'] != 'owner':
        raise HTTPException(403, 'Only a team owner can create invitations.')
    role = payload.get('role', 'editor')
    if role not in ('viewer', 'editor'):
        raise ValueError('Choose viewer or editor access.')
    token = secrets.token_urlsafe(32)
    store.put('team_invites', hashlib.sha256(token.encode()).hexdigest(), 'system',
              {'team_id': team_id, 'role': role, 'expires': time.time() + 86400})
    return {'code': token, 'expires_in': 86400}


@router.post('/join')
def join(payload: dict):
    user = require_account()
    code = str(payload.get('code', ''))
    if len(code) > 200:
        raise ValueError('Invalid invitation.')
    record = store.take('team_invites', hashlib.sha256(code.encode()).hexdigest(), 'system')
    if not record or record['expires'] < time.time():
        raise ValueError('The invitation expired or has already been used.')
    existing = store.get('team_members', record['team_id'] + ':' + user['id'], user['id'])
    return existing or store.put('team_members', record['team_id'] + ':' + user['id'], user['id'],
                                 {'team_id': record['team_id'], 'role': record['role'], 'name': user['name']})


@router.post('/{team_id}/share')
def share(team_id: str, payload: dict):
    member(team_id, True)
    project_id = str(payload.get('project_id', ''))
    original = store.get('projects', project_id, owner())
    if not original:
        raise HTTPException(404, 'Choose one of your projects to share.')
    # Explicitly make a shared copy so personal credentials, jobs and projects stay private.
    identity = str(uuid.uuid4())
    files = list(original.get('files', []))
    for path in files:
        store.put_blob(team_id, 'projects/' + identity + '/' + path,
                       store.get_blob(owner(), 'projects/' + project_id + '/' + path).read_bytes())
    def relink(value):
        if isinstance(value, str):
            if value.startswith('/api/editor/projects/' + project_id + '/files/'):
                return value.replace('/api/editor/projects/' + project_id + '/', '/api/editor/projects/' + identity + '/', 1)
            for prefix, folder in (('/api/uploads/', 'uploads/'), ('/api/editor/assets/file/', '')):
                if value.startswith(prefix):
                    source = folder + value[len(prefix):]
                    path = 'shared/' + source
                    if path not in files:
                        store.put_blob(team_id, 'projects/' + identity + '/' + path, store.get_blob(owner(), source).read_bytes())
                        files.append(path)
                    return '/api/editor/projects/' + identity + '/files/' + path
            return value
        if isinstance(value, list):
            return [relink(child) for child in value]
        if isinstance(value, dict):
            return {key: relink(child) for key, child in value.items()}
        return value
    project = copy.deepcopy(original)
    for sequence in project.get('sequences', []):
        if sequence.get('kind') != 'rayflow':
            continue
        document = sequence.get('document', {})
        assets = {row.get('filename'): row.get('url') for row in document.get('images', [])}
        for clip in document.get('plan', {}).get('clips', []):
            clip['image_url'] = assets.get(clip.get('image_url')) or clip.get('image_url')
        for row in document.get('images', []) + ([document['audio']] if document.get('audio') else []):
            row['filename'] = row.get('url') or row.get('filename')
    project = relink(project)
    project.update(name=original['name'] + ' (team)', files=files, assets=[], team_id=team_id)
    result = store.put('projects', identity, team_id, project)
    store.put('shared_project_access', identity, 'system', {'team_id': team_id})
    return result


@router.get('/{team_id}/activity')
def activity(team_id: str):
    member(team_id)
    return {'messages': store.list('team_chat', team_id)[:100],
            'presence': [row for row in store.list('team_presence', team_id) if row['seen'] > time.time() - 45]}


@router.post('/{team_id}/activity')
def publish(team_id: str, payload: dict):
    membership = member(team_id)
    user = require_account()
    store.put('team_presence', team_id + ':' + user['id'], team_id,
              {'name': user['name'], 'user_id': user['id'], 'role': membership['role'], 'seen': time.time()})
    message = payload.get('message')
    if message:
        if not isinstance(message, str) or len(message) > 4000:
            raise ValueError('Chat messages must be at most 4000 characters.')
        store.put('team_chat', str(uuid.uuid4()), team_id,
                  {'name': user['name'], 'message': message, 'created': time.time(), 'project_id': payload.get('project_id')})
    return {'ok': True}
