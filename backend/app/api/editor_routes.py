"""First-class editor API. Every handler runs in the authenticated workspace."""
import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request, Response, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.editor.context import owner, workspace_id
from app.editor.store import store, safe_relative, Conflict, StorageUnavailable
from app.editor.security import COOKIE, create_session, resolve_session, set_cookie, end_session, session_public, require_origin
from app.editor.providers import public_providers, save_provider, delete_provider, test_provider, proxy_request
from app.editor import jobs

router = APIRouter(tags=['integrated-editor'])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProviderPatch(StrictModel):
    key: str | None = None
    model: str | None = None


class ProjectPatch(StrictModel):
    name: str = Field(default='Untitled project', min_length=1, max_length=200)
    project: dict = Field(default_factory=dict)
    revision: int | None = None
    document_revision: int | None = None
    kind: str = 'editor'


class JobRequest(StrictModel):
    kind: str
    payload: dict
    submission_key: str = Field(min_length=1, max_length=128)


class SequencePatch(StrictModel):
    kind: str
    name: str = Field(default='Untitled sequence', max_length=200)
    document: dict
    revision: int = Field(ge=0)


class FileWrite(StrictModel):
    data: str
    encoding: str = 'utf8'


def ensure_project(identity, write=False):
    from app.editor.teams import project_owner
    workspace_id.set(project_owner(identity, write))
    record = store.get('projects', identity, owner())
    if not record:
        raise HTTPException(404, 'Project not found.')
    return record


def no_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r'(?:api[_-]?key|access[_-]?token|refresh[_-]?token|service[_-]?role[_-]?key|^hfToken$|client[_-]?secret|^password$)', key, re.I):
                raise ValueError('Store credentials in Connections, not in project documents.')
            no_secrets(child)
    elif isinstance(value, list):
        for item in value:
            no_secrets(item)


@router.post('/api/session')
def initialize_session(request: Request):
    require_origin(request)
    token = request.cookies.get(COOKIE)
    record = resolve_session(token)
    if not record:
        token, record = create_session()
    context_token = workspace_id.set(record['workspace_id'])
    try:
        jobs.recover_for_workspace()
        response = JSONResponse(session_public())
        set_cookie(response, token)
        response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        workspace_id.reset(context_token)


@router.get('/api/session')
def get_session():
    return session_public()


@router.delete('/api/session')
def close_session(request: Request):
    require_origin(request)
    end_session(request.cookies.get(COOKIE))
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE, path='/')
    return response


@router.put('/api/editor/preferences')
def preferences(value: dict):
    no_secrets(value)
    return store.put('preferences', owner(), owner(), value)


@router.patch('/api/editor/preferences')
def patch_preferences(value: dict):
    no_secrets(value)
    def merge(current, patch):
        for key, child in patch.items():
            if key in ('id', 'revision', 'owner_id'):
                continue
            if isinstance(child, dict) and isinstance(current.get(key), dict):
                merge(current[key], child)
            else:
                current[key] = child
        return current
    with store.lock:
        current = store.get('preferences', owner(), owner()) or {}
        return store.put('preferences', owner(), owner(), merge(current, value), expected=current.get('revision', 0))


@router.get('/api/editor/providers')
def providers():
    return {'providers': public_providers()}


@router.put('/api/editor/providers/{provider}')
def update_provider(provider: str, patch: ProviderPatch):
    save_provider(provider, patch.key, patch.model)
    return {'providers': public_providers()}


@router.delete('/api/editor/providers/{provider}')
def remove_provider(provider: str):
    delete_provider(provider)
    return {'providers': public_providers()}


@router.post('/api/editor/providers/{provider}/test')
def verify_provider(provider: str, patch: ProviderPatch = None):
    if provider in ('openai', 'anthropic', 'agentrouter', 'gemini') and patch and (patch.key or patch.model):
        from app.services.ai_provider import test_connection, MODELS
        from app.editor.providers import provider_record
        record = provider_record(provider) or {}
        if patch.key or patch.model != (record.get('model') or (MODELS.get(provider) or ['gpt-6-astra'])[0]):
            return test_connection(provider, patch.key, patch.model)
    return test_provider(provider)


@router.get('/api/editor/providers/{provider}/models')
def provider_models(provider: str):
    if provider == 'gemini':
        from app.services.ai_provider import gemini_models
        return {'models': gemini_models()}
    paths = {'gemini': 'https://generativelanguage.googleapis.com/v1beta/models',
             'openrouter': 'https://openrouter.ai/api/v1/models', 'xai': 'https://api.x.ai/v1/models',
             'ollama': 'http://127.0.0.1:11434/api/tags', 'lmstudio': 'http://127.0.0.1:1234/v1/models',
             'openai-compatible': 'http://127.0.0.1:8080/v1/models'}
    if provider == 'agentrouter':
        from app.services.ai_provider import agentrouter_base
        paths[provider] = agentrouter_base() + '/models'
    if provider not in paths:
        return {'models': [], 'catalog': True}
    result = proxy_request(provider, paths[provider])
    if result['status'] != 200:
        raise HTTPException(result['status'], 'Model discovery failed. Check the connection.')
    data = json.loads(result.get('text', '{}'))
    values = data.get('models', data.get('data', []))
    return {'models': [item.get('name', item.get('id', '')) for item in values]}


@router.get('/api/editor/capabilities')
def capabilities():
    from app.core.config import FFMPEG_PATH
    from app.editor.capabilities import codec_capabilities
    import shutil
    import importlib.util
    runtime = Path(__file__).resolve().parents[2] / 'editor-runtime'
    processors = {}
    for name, dependencies in {'audio-mastering': ('librosa', 'soundfile', 'pyloudnorm'),
                               'audio-remaster': ('matchering',)}.items():
        missing = [dependency for dependency in dependencies if importlib.util.find_spec(dependency) is None]
        processors[name] = {'available': not missing, 'ready': not missing,
                            'error': 'Backend operator must install: ' + ', '.join(missing) if missing else None}
    depth_repo = Path(os.getenv('EDITOR_SURFACE_MAP_REPO', '/not-configured'))
    depth_ready = (depth_repo / 'run.py').is_file() and (depth_repo / 'checkpoints').is_dir()
    key_repo = Path(os.getenv('EDITOR_CORRIDOR_KEY_REPO', '/not-configured'))
    key_ready = (key_repo / 'corridorkey_cli.py').is_file() and bool(shutil.which('uv'))
    processors['surface-map'] = {'available': True, 'ready': depth_ready, 'depthGradientReady': True,
        'error': None if depth_ready else 'The backend operator must provision Depth Anything V2 and its weights. Depth-gradient normal maps are available.'}
    processors['corridor-key'] = {'available': key_ready, 'ready': key_ready,
        'error': None if key_ready else 'The backend operator must provision CorridorKey, uv, dependencies and model weights.'}
    return {'storage': 'supabase' if store.cloud else 'local', 'providers': public_providers(),
            'ffmpeg': bool(shutil.which(FFMPEG_PATH) or Path(FFMPEG_PATH).is_file()),
            'codecs': codec_capabilities(FFMPEG_PATH),
            'exports': {
                'browser': {'video': True, 'audio': False, 'format': 'WebM',
                            'reason': 'Browser recording captures the visual canvas. Use HQ FFmpeg for timeline audio.'},
                'ffmpeg': {'video': True, 'audio': True, 'volume_keyframes': True, 'custom_luts': True,
                           'unsupported': ['text overlays', 'transitions', 'chroma key', 'non-normal blend modes',
                                           'opacity keyframes', 'pan automation', 'untyped audio effects']},
            },
            'node_runtime': bool(shutil.which('node') and all((runtime / 'node_modules' / module / 'package.json').is_file()
                                for module in ('@google/genai', 'fluent-ffmpeg'))),
            'payments': False, 'desktop': False, 'processors': processors,
            'optional': {'notebooklm': bool(os.getenv('EDITOR_NOTEBOOKLM_URL')),
                         'collaboration': True, 'accounts': store.cloud, 'teams': store.cloud},
            'unavailable': {'midjourney': 'This integration requires an interactive native login window.',
                            'native_agents': 'Native agent login windows are unavailable in the hosted runtime.',
                            'world_mesh_conversion': 'The upstream world provider does not implement mesh conversion.'}}


@router.get('/api/editor/projects')
def projects():
    from app.editor.teams import shared_projects
    return {'projects': store.list('projects', owner()) + shared_projects()}


@router.post('/api/editor/projects')
def create_project(patch: ProjectPatch):
    no_secrets(patch.project)
    identity = str(uuid.uuid4())
    return store.put('projects', identity, owner(), {'name': patch.name, 'project': patch.project,
                     'kind': patch.kind, 'version': 2, 'document_revision': 1,
                     'sequences': [], 'assets': [], 'production': {},
                     'created': time.time(), 'updated': time.time(), 'files': []})


@router.get('/api/editor/projects/{identity}')
def project(identity: str):
    from app.editor.teams import project_role
    record = ensure_project(identity)
    return {**record, 'read_only': project_role(identity) == 'viewer'}


@router.put('/api/editor/projects/{identity}')
def update_project(identity: str, patch: ProjectPatch):
    existing = ensure_project(identity, write=True)
    no_secrets(patch.project)
    current_document_revision = existing.get('document_revision', 1)
    if patch.document_revision is not None and patch.document_revision != current_document_revision:
        raise Conflict('The document changed elsewhere. Reload it or save a copy before replacing it.')
    if patch.document_revision is None and patch.revision is None:
        raise HTTPException(428, 'Send the revision loaded with this project before saving.')
    existing.update(name=patch.name, project=patch.project, kind=patch.kind, updated=time.time())
    existing['document_revision'] = current_document_revision + 1
    sequences = [sequence for sequence in existing.get('sequences', []) if sequence['id'] != 'editor-primary']
    sequences.append({'id': 'editor-primary', 'kind': 'editor', 'name': patch.name,
                      'document': patch.project, 'revision': existing['document_revision']})
    existing['sequences'] = sequences
    return store.put('projects', identity, owner(), existing,
                     expected=existing['revision'] if patch.document_revision is not None else patch.revision)


@router.put('/api/editor/projects/{identity}/sequences/{sequence_id}')
def save_sequence(identity: str, sequence_id: str, patch: SequencePatch):
    if patch.kind not in ('rayflow', 'editor') or not sequence_id or len(sequence_id) > 128:
        raise ValueError('Unsupported sequence type or identifier.')
    if sequence_id == 'editor-primary':
        raise ValueError('Save the primary editor document through the project endpoint.')
    no_secrets(patch.document)
    existing = ensure_project(identity, write=True)
    sequences = existing.get('sequences', [])
    current = next((sequence for sequence in sequences if sequence['id'] == sequence_id), None)
    if (current['revision'] if current else 0) != patch.revision:
        raise Conflict('This sequence changed elsewhere. Reload or create a copy before saving.')
    if current and current['kind'] != patch.kind:
        raise ValueError('Changing a sequence schema requires an explicit conversion into a new sequence.')
    saved = {'id': sequence_id, 'kind': patch.kind, 'name': patch.name,
             'document': patch.document, 'revision': patch.revision + 1}
    existing['sequences'] = [sequence for sequence in sequences if sequence['id'] != sequence_id] + [saved]
    existing['updated'] = time.time()
    store.put('projects', identity, owner(), existing, expected=existing['revision'])
    return saved


@router.delete('/api/editor/projects/{identity}')
def delete_project(identity: str):
    record = ensure_project(identity, write=True)
    for relative in record.get('files', []):
        store.delete_blob(owner(), 'projects/' + identity + '/' + safe_relative(relative))
    store.delete('projects', identity, owner())
    return {'ok': True}


@router.post('/api/editor/projects/{identity}/sequences/{sequence_id}/transfer')
def transfer_sequence(identity: str, sequence_id: str, payload: dict):
    from app.editor.sequences import transfer
    existing = ensure_project(identity, write=True)
    if payload.get('revision') != existing['revision']:
        raise Conflict('The project changed. Refresh its sequences before transferring.')
    source = next((row for row in existing.get('sequences', []) if row['id'] == sequence_id), None)
    if not source:
        raise HTTPException(404, 'Sequence not found.')
    destination = payload.get('kind')
    if destination not in ('editor', 'rayflow'):
        raise ValueError('Choose an editor timeline or Rayflow reel.')
    document = transfer(source, destination, identity)
    sequence = {'id': str(uuid.uuid4()), 'kind': destination, 'name': source['name'] + ' copy',
                'revision': 1, 'document': document}
    existing.setdefault('sequences', []).append(sequence)
    store.put('projects', identity, owner(), existing, expected=existing['revision'])
    return sequence


@router.post('/api/editor/projects/{identity}/sequences/{sequence_id}/activate')
def activate_sequence(identity: str, sequence_id: str, payload: dict):
    import copy
    existing = ensure_project(identity, write=True)
    if payload.get('revision') != existing['revision']:
        raise Conflict('The project changed. Refresh its sequences before opening.')
    sequences = existing.get('sequences', [])
    source = next((row for row in sequences if row['id'] == sequence_id), None)
    if not source:
        raise HTTPException(404, 'Sequence not found.')
    primary = 'editor-primary' if source['kind'] == 'editor' else 'reel-primary'
    if sequence_id != primary:
        previous = next((row for row in sequences if row['id'] == primary), None)
        if previous:
            sequences.append({**copy.deepcopy(previous), 'id': str(uuid.uuid4()), 'name': previous['name'] + ' before switch'})
        revision = (previous['revision'] if previous else 0) + 1
        existing['sequences'] = [row for row in sequences if row['id'] != primary] + [{**copy.deepcopy(source), 'id': primary, 'revision': revision}]
        if source['kind'] == 'editor':
            existing['project'] = copy.deepcopy(source['document'])
            existing['document_revision'] = existing.get('document_revision', 1) + 1
        existing = store.put('projects', identity, owner(), existing, expected=existing['revision'])
    return {'project': existing, 'workspace': 'editor' if source['kind'] == 'editor' else 'studio'}


@router.get('/api/editor/projects/{identity}/archive')
def project_archive(identity: str):
    record = ensure_project(identity)
    output = io.BytesIO()
    shared_paths = set()
    def find_shared(value):
        if isinstance(value, str):
            for prefix, folder in (('/api/uploads/', 'uploads/'), ('/api/editor/assets/file/', '')):
                if value.startswith(prefix):
                    shared_paths.add(safe_relative(folder + value[len(prefix):]))
        elif isinstance(value, dict):
            for child in value.values():
                find_shared(child)
        elif isinstance(value, list):
            for child in value:
                find_shared(child)
    find_shared(record)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('rayflow-project.json', json.dumps(record))
        manifest = {}
        for index, relative in enumerate(sorted(shared_paths)):
            path = store.get_blob(owner(), relative)
            entry = '__shared__/' + str(index) + path.suffix
            archive.write(path, entry)
            manifest[entry] = relative
        archive.writestr('rayflow-assets.json', json.dumps(manifest))
        for relative in record.get('files', []):
            path = store.get_blob(owner(), 'projects/' + identity + '/' + safe_relative(relative))
            archive.write(path, relative)
    return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="rayflow-project.zip"'})


@router.post('/api/editor/project-import')
def import_project(file: UploadFile = File(...)):
    from app.core.config import MAX_UPLOAD_MB
    content = file.file.read(MAX_UPLOAD_MB * 1024**2 + 1)
    if len(content) > MAX_UPLOAD_MB * 1024**2:
        raise HTTPException(413, 'Project archive is too large.')
    assets = {}
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(item.file_size for item in entries) > MAX_UPLOAD_MB * 1024**2:
                raise HTTPException(413, 'Expanded project archive is too large.')
            for entry in entries:
                if not entry.is_dir():
                    assets[safe_relative(entry.filename)] = archive.read(entry)
            candidate = assets.pop('rayflow-project.json', None) or assets.pop('project.json', None)
            if not candidate:
                raise ValueError('The archive needs rayflow-project.json or project.json.')
            data = json.loads(candidate)
    else:
        data = json.loads(content)
    shared_manifest = json.loads(assets.pop('rayflow-assets.json', b'{}'))
    replacements = {}
    for entry, original in shared_manifest.items():
        original = safe_relative(original)
        entry = safe_relative(entry)
        if entry not in assets:
            raise ValueError('A shared asset listed in the archive is missing.')
        content = assets.pop(entry)
        filename = 'imported_' + uuid.uuid4().hex + Path(original).suffix
        relative = ('uploads/' if original.startswith('uploads/') else 'assets/') + filename
        store.put_blob(owner(), relative, content)
        old_url = '/api/uploads/' + original[8:] if original.startswith('uploads/') else '/api/editor/assets/file/' + original
        new_url = '/api/uploads/' + filename if relative.startswith('uploads/') else '/api/editor/assets/file/' + relative
        replacements[old_url] = new_url
        replacements[original] = relative
        if original.startswith('uploads/'):
            replacements[original[8:]] = filename
        store.put('assets', filename, owner(), {'name': Path(original).name, 'path': relative, 'url': new_url,
                  'size': len(content), 'type': (mimetypes.guess_type(filename)[0] or 'file').split('/')[0]})
    snapshot = data.get('project', data)
    record = create_project(ProjectPatch(name=data.get('name') or snapshot.get('name') or 'Imported project', project=snapshot))
    for relative, content in assets.items():
        store.put_blob(owner(), 'projects/' + record['id'] + '/' + relative, content)
    record['files'] = list(assets)
    # Preserve both timeline schemas and production metadata in archives.
    for field in ('sequences', 'assets', 'production'):
        if field in data:
            no_secrets(data[field])
            record[field] = data[field]
    def relink(value):
        if isinstance(value, str):
            value = replacements.get(value, value)
            if data.get('id'):
                value = value.replace('/api/editor/projects/' + str(data['id']) + '/files/',
                                      '/api/editor/projects/' + record['id'] + '/files/')
            return value
        if isinstance(value, list):
            return [relink(child) for child in value]
        if isinstance(value, dict):
            return {key: relink(child) for key, child in value.items()}
        return value
    record = relink(record)
    return store.put('projects', record['id'], owner(), record)


@router.get('/api/editor/projects/{identity}/files/{relative:path}')
def read_project_file(identity: str, relative: str):
    ensure_project(identity)
    if store.cloud:
        return RedirectResponse(store.sign(owner(), 'projects/' + identity + '/' + safe_relative(relative))['url'], status_code=307)
    path = store.get_blob(owner(), 'projects/' + identity + '/' + safe_relative(relative))
    return FileResponse(path)


@router.put('/api/editor/projects/{identity}/files/{relative:path}')
async def write_project_file(identity: str, relative: str, request: Request):
    record = ensure_project(identity, write=True)
    relative = safe_relative(relative)
    if relative in ('rayflow-project.json', 'rayflow-assets.json') or relative.startswith('__shared__/'):
        raise ValueError('This file name is reserved for project archives.')
    content = await request.body()
    from app.core.config import MAX_UPLOAD_MB
    if len(content) > MAX_UPLOAD_MB * 1024**2:
        raise HTTPException(413, 'File exceeds the upload limit.')
    store.put_blob(owner(), 'projects/' + identity + '/' + relative, content, request.headers.get('content-type'))
    record = ensure_project(identity)
    record['files'] = sorted(set(record.get('files', []) + [relative]))
    store.put('projects', identity, owner(), record)
    return {'ok': True, 'relativePath': relative}


@router.post('/api/editor/projects/{identity}/file-ticket')
def project_file_ticket(identity: str, payload: dict):
    ensure_project(identity, write=True)
    relative = safe_relative(payload.get('relativePath', ''))
    if not relative.startswith('objects/'):
        raise ValueError('Direct project uploads must use immutable object paths.')
    return store.sign(owner(), 'projects/' + identity + '/' + relative, upload=True)


@router.post('/api/editor/projects/{identity}/file-complete')
def project_file_complete(identity: str, payload: dict):
    record = ensure_project(identity, write=True)
    relative = safe_relative(payload.get('relativePath', ''))
    if not relative.startswith('objects/'):
        raise ValueError('Direct project uploads must use immutable object paths.')
    from app.core.config import MAX_UPLOAD_MB
    size = store.blob_size(owner(), 'projects/' + identity + '/' + relative)
    if size > MAX_UPLOAD_MB * 1024**2:
        raise HTTPException(413, 'File exceeds the upload limit.')
    record['files'] = sorted(set(record.get('files', []) + [relative]))
    store.put('projects', identity, owner(), record, expected=record['revision'])
    return {'ok': True, 'size': size}


@router.delete('/api/editor/projects/{identity}/files/{relative:path}')
def remove_project_file(identity: str, relative: str):
    record = ensure_project(identity, write=True)
    relative = safe_relative(relative)
    store.delete_blob(owner(), 'projects/' + identity + '/' + relative)
    record['files'] = [name for name in record.get('files', []) if name != relative]
    store.put('projects', identity, owner(), record)
    return {'ok': True}


@router.get('/api/editor/assets')
def assets():
    return {'assets': store.list('assets', owner())}


@router.post('/api/editor/assets')
def upload_asset(file: UploadFile = File(...)):
    from app.core.config import MAX_UPLOAD_MB
    content = file.file.read(MAX_UPLOAD_MB * 1024**2 + 1)
    if len(content) > MAX_UPLOAD_MB * 1024**2:
        raise HTTPException(413, 'File exceeds the upload limit.')
    identity = str(uuid.uuid4())
    ext = Path(file.filename or '').suffix.lower()
    if len(ext) > 12 or not ext.replace('.', '').isalnum():
        ext = '.bin'
    relative = 'assets/' + identity + ext
    store.put_blob(owner(), relative, content, file.content_type)
    return store.put('assets', identity, owner(), {'name': file.filename, 'path': relative,
                     'type': (file.content_type or '').split('/')[0], 'size': len(content),
                     'url': '/api/editor/assets/file/' + relative})


@router.post('/api/editor/assets/upload-ticket')
def upload_ticket(payload: dict):
    from app.core.config import MAX_UPLOAD_MB
    size = payload.get('size', 0)
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_UPLOAD_MB * 1024**2:
        raise ValueError('Choose a nonempty file within the configured upload limit.')
    identity = str(uuid.uuid4())
    name = str(payload.get('name', 'asset'))[:200]
    relative = 'assets/' + identity + (Path(name).suffix if len(Path(name).suffix) < 12 else '.bin')
    ticket = store.sign(owner(), relative, upload=True)
    record = store.put('assets', identity, owner(), {'name': name, 'path': relative, 'pending': True,
                       'type': str(payload.get('type', 'file')).split('/')[0], 'size': payload.get('size', 0)})
    return {'asset': record, 'upload': ticket}


@router.post('/api/editor/assets/{identity}/complete')
def complete_asset(identity: str):
    record = store.get('assets', identity, owner())
    if not record:
        raise HTTPException(404, 'Asset not found.')
    size = store.blob_size(owner(), record['path'])
    from app.core.config import MAX_UPLOAD_MB
    if size > MAX_UPLOAD_MB * 1024**2:
        raise HTTPException(413, 'File exceeds the upload limit.')
    record.update(pending=False, size=size, url='/api/editor/assets/file/' + record['path'])
    return store.put('assets', identity, owner(), record)


@router.get('/api/editor/assets/file/{relative:path}')
def asset_file(relative: str):
    if store.cloud:
        return RedirectResponse(store.sign(owner(), safe_relative(relative))['url'], status_code=307)
    return FileResponse(store.get_blob(owner(), safe_relative(relative)))


@router.post('/api/editor/assets/{identity}/studio')
def asset_to_studio(identity: str):
    from app.services.media import probe_media, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
    asset = store.get('assets', identity, owner())
    if not asset or asset.get('pending'):
        raise HTTPException(404, 'Asset not found.')
    source = store.get_blob(owner(), asset['path'])
    ext = source.suffix.lower()
    kind = 'image' if ext in IMAGE_EXTENSIONS else 'video' if ext in VIDEO_EXTENSIONS else asset.get('type')
    if kind not in ('image', 'video', 'audio'):
        raise ValueError('This asset cannot be used by the Studio timeline. Import an image, video, or audio file.')
    if kind == 'image':
        from PIL import Image
        with Image.open(source) as image:
            image.verify()
    filename = 'shared_' + hashlib.sha256(asset['path'].encode()).hexdigest()[:24] + ext
    metadata = probe_media(source) if kind != 'image' else {}
    if kind == 'video' and not metadata.get('has_video') or kind == 'audio' and not metadata.get('has_audio'):
        raise ValueError('This file does not contain the expected media stream.')
    store.put_blob(owner(), 'uploads/' + filename, source.read_bytes())
    return {'filename': filename, 'original_name': asset.get('name', filename), 'size': source.stat().st_size,
            'url': '/api/uploads/' + filename, 'media_type': kind, **metadata}


@router.post('/api/editor/assets/download-ticket')
def asset_ticket(payload: dict):
    relative = safe_relative(payload['path'])
    return store.sign(owner(), relative) or {'url': '/api/editor/assets/file/' + relative}


@router.post('/api/editor/jobs')
def submit_job(request: JobRequest):
    return jobs.submit(request.kind, request.payload, request.submission_key)


@router.get('/api/editor/jobs')
def list_jobs():
    jobs.recover_for_workspace()
    return {'jobs': [jobs.public_job(row) for row in store.list('jobs', owner())]}


@router.get('/api/editor/jobs/{identity}')
def job(identity: str):
    record = store.get('jobs', identity, owner())
    if not record:
        raise HTTPException(404, 'Job not found.')
    return jobs.public_job(record)


@router.post('/api/editor/jobs/{identity}/cancel')
def cancel_job(identity: str):
    return jobs.cancel(identity)


@router.post('/api/editor/jobs/{identity}/retry')
def retry_job(identity: str):
    return jobs.retry(identity)


@router.post('/api/editor/jobs/{identity}/provider-status')
def provider_job_status(identity: str):
    return jobs.refresh_provider(identity)
