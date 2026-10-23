"""Private durable Yjs updates and authenticated presence for shared projects."""
import base64
import hashlib
import json
import time
import uuid
from fastapi import APIRouter, HTTPException
from .context import account, owner
from .store import store
from .teams import project_owner, project_role

router = APIRouter(prefix='/api/editor/collaboration', tags=['collaboration'])


def collection(project_id, name):
    return 'collab_' + name + ':' + project_id


@router.get('/{project_id}')
def read(project_id: str):
    identity = project_owner(project_id)
    return {'readOnly': project_role(project_id) == 'viewer',
            'updates': store.list(collection(project_id, 'updates'), identity),
            'presence': [row for row in store.list(collection(project_id, 'presence'), identity) if row['seen'] > time.time() - 30],
            'events': store.list(collection(project_id, 'events'), identity)[:100]}


@router.post('/{project_id}')
def publish(project_id: str, payload: dict):
    identity = project_owner(project_id, write=bool(payload.get('update') or payload.get('event')))
    user = account.get() or {'id': owner(), 'name': 'Guest'}
    session = str(payload.get('session', ''))
    if not session or len(session) > 150:
        raise ValueError('A collaboration session identifier is required.')
    actor = hashlib.sha256((user['id'] + ':' + session).encode()).hexdigest()
    presence = payload.get('presence', {})
    if not isinstance(presence, dict) or len(json.dumps(presence)) > 20_000:
        raise ValueError('Invalid collaboration presence.')
    if payload.get('leave'):
        store.delete(collection(project_id, 'presence'), actor, identity)
        return {'ok': True}
    store.put(collection(project_id, 'presence'), actor, identity,
              {'sessionId': session, 'collaboratorId': user['id'], 'collaboratorName': user['name'],
               'selection': presence.get('selection'), 'workspace': presence.get('workspace'), 'status': presence.get('status', 'active'),
               'role': project_role(project_id), 'seen': time.time(), 'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    if payload.get('update'):
        content = base64.b64decode(payload['update'], validate=True)
        if len(content) > 2_000_000:
            raise HTTPException(413, 'Collaboration update is too large.')
        digest = hashlib.sha256(content).hexdigest()
        if not store.get(collection(project_id, 'updates'), digest, identity):
            store.put(collection(project_id, 'updates'), digest, identity, {'data': payload['update'], 'created': time.time()})
    if payload.get('event'):
        event = payload['event']
        from app.api.editor_routes import no_secrets
        no_secrets(event)
        if not isinstance(event, dict) or len(json.dumps(event)) > 100_000:
            raise ValueError('Collaboration event is too large.')
        store.put(collection(project_id, 'events'), str(uuid.uuid4()), identity,
                  {**event, 'actor': {'id': user['id'], 'name': user['name'], 'sessionId': session, 'role': 'editor'},
                   'projectId': project_id, 'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    return {'ok': True}
