"""Owner-scoped records and private blobs.

Three backends, selected by environment:
  * GCS (recommended for Cloud Run): records as JSON objects + media as blobs in
    one private bucket. No external database required. Set GCS_BUCKET.
  * Supabase: records table + storage bucket (legacy hosted option).
  * Local SQLite + filesystem: development/tests only.

The service-role credential is never returned to a browser. All public access
passes the owner predicate here.
"""
import json
import mimetypes
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import requests


class Conflict(ValueError):
    pass


class StorageUnavailable(RuntimeError):
    pass


def root_path():
    from app.core.config import BASE_DIR
    return Path(os.getenv('RAYFLOW_STORAGE_DIR', str(BASE_DIR / 'storage'))).resolve()


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Invalid file path.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('..', '.', '') for part in value.split('/')) or ':' in value:
        raise ValueError('File paths must stay inside the project.')
    return path.as_posix()


class RecordStore:
    def __init__(self):
        self.lock = threading.RLock()

    @property
    def cloud(self):
        return bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

    @property
    def gcs_bucket(self):
        """When set, blobs (media/exports) are stored in Google Cloud Storage.

        Records still use Supabase/SQLite; only large binary objects go to GCS so
        user media survives Cloud Run's ephemeral filesystem. Enabled by setting
        GCS_BUCKET to the bucket name (no gs:// prefix).
        """
        return os.getenv('GCS_BUCKET', '').strip() or None

    def _check(self):
        # Production needs durable, cross-instance storage. Either a GCS bucket
        # (records + blobs in one bucket, no external DB) or Supabase satisfies
        # this; local SQLite is only for development/tests.
        if os.getenv('RAYFLOW_ENV') == 'production' and not self.cloud and not self.gcs_bucket:
            raise StorageUnavailable('Configure GCS_BUCKET (recommended) or Supabase on the backend.')

    def request(self, method, path, **kwargs):
        self._check()
        headers = {'apikey': os.environ['SUPABASE_SERVICE_ROLE_KEY'],
                   'Authorization': 'Bearer ' + os.environ['SUPABASE_SERVICE_ROLE_KEY']}
        headers.update(kwargs.pop('headers', {}))
        try:
            result = requests.request(method, os.environ['SUPABASE_URL'].rstrip('/') + path,
                                      headers=headers, timeout=(10, 90), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise StorageUnavailable('The private project store could not be reached. Retry shortly.') from None
        if result.status_code == 409:
            raise Conflict('The project changed elsewhere. Reload before saving.')
        if not 200 <= result.status_code < 300:
            raise StorageUnavailable(f'Private storage returned HTTP {result.status_code}. Check backend configuration and migrations.')
        return result

    def _db(self):
        self._check()
        directory = root_path() / 'private'
        directory.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(directory / 'editor.sqlite3', timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS records (collection TEXT, id TEXT, owner TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL, updated REAL NOT NULL, PRIMARY KEY(collection,id))')
        return db

    def list(self, collection, owner_id, identity=None):
        if self.gcs_bucket:
            from app.editor import gcs
            if identity is not None:
                found = gcs.get_record(collection, owner_id, identity)
                if not found:
                    return []
                payload, revision, _gen = found
                return [dict(payload, id=identity, revision=revision)]
            return [dict(payload, id=rid, revision=revision)
                    for rid, payload, revision in gcs.list_records(collection, owner_id)]
        if self.cloud:
            params = {'collection': 'eq.' + collection, 'owner_id': 'eq.' + owner_id, 'select': '*', 'order': 'updated.desc'}
            if identity is not None:
                params['id'] = 'eq.' + identity
            rows = []
            while True:
                page = self.request('GET', '/rest/v1/rayflow_records', params={**params, 'limit': 500, 'offset': len(rows)}).json()
                rows.extend(page)
                if len(page) < 500:
                    break
            return [dict(row['payload'], id=row['id'], revision=row['revision']) for row in rows]
        with self.lock, self._db() as db:
            query = 'SELECT * FROM records WHERE collection=? AND owner=?'
            args = [collection, owner_id]
            if identity is not None:
                query += ' AND id=?'
                args.append(identity)
            rows = db.execute(query + ' ORDER BY updated DESC', args).fetchall()
            return [dict(json.loads(row['payload']), id=row['id'], revision=row['revision']) for row in rows]

    def get(self, collection, identity, owner_id):
        values = self.list(collection, owner_id, identity)
        return values[0] if values else None

    def put(self, collection, identity, owner_id, payload, expected=None):
        if self.gcs_bucket:
            from app.editor import gcs
            with self.lock:
                found = gcs.get_record(collection, owner_id, identity)
                revision = found[1] if found else 0
                generation = found[2] if found else 0  # 0 => object must not exist
                if expected is not None and expected != revision:
                    raise Conflict('The project changed elsewhere. Reload before saving.')
                clean = {k: v for k, v in payload.items() if k not in ('id', 'revision', 'owner_id')}
                next_revision = revision + 1
                if not gcs.put_record(collection, owner_id, identity, clean, next_revision,
                                      expected_generation=generation):
                    raise Conflict('The project changed elsewhere. Reload before saving.')
                return dict(clean, id=identity, revision=next_revision)
        with self.lock:
            current = self.get(collection, identity, owner_id)
            revision = current['revision'] if current else 0
            if expected is not None and expected != revision:
                raise Conflict('The project changed elsewhere. Reload before saving.')
            clean = {k: v for k, v in payload.items() if k not in ('id', 'revision', 'owner_id')}
            next_revision = revision + 1
            if self.cloud:
                row = {'collection': collection, 'id': identity, 'owner_id': owner_id,
                       'payload': clean, 'revision': next_revision, 'updated': time.time()}
                if current:
                    result = self.request('PATCH', '/rest/v1/rayflow_records',
                                          params={'collection': 'eq.' + collection, 'id': 'eq.' + identity,
                                                  'owner_id': 'eq.' + owner_id, 'revision': 'eq.' + str(revision)},
                                          headers={'Prefer': 'return=representation'}, json=row).json()
                    if not result:
                        raise Conflict('The project changed elsewhere. Reload before saving.')
                else:
                    self.request('POST', '/rest/v1/rayflow_records', json=row)
            else:
                with self._db() as db:
                    if current:
                        result = db.execute('UPDATE records SET payload=?,revision=?,updated=? WHERE collection=? AND id=? AND owner=? AND revision=?',
                                            (json.dumps(clean), next_revision, time.time(), collection, identity, owner_id, revision))
                        if result.rowcount != 1:
                            raise Conflict('The project changed elsewhere. Reload before saving.')
                    else:
                        try:
                            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?)', (collection, identity, owner_id, json.dumps(clean), next_revision, time.time()))
                        except sqlite3.IntegrityError:
                            raise Conflict('Record already exists.') from None
            return dict(clean, id=identity, revision=next_revision)

    def delete(self, collection, identity, owner_id):
        if self.gcs_bucket:
            from app.editor import gcs
            gcs.delete_record(collection, owner_id, identity)
            return
        if self.cloud:
            self.request('DELETE', '/rest/v1/rayflow_records', params={'collection': 'eq.' + collection, 'id': 'eq.' + identity, 'owner_id': 'eq.' + owner_id})
        else:
            with self.lock, self._db() as db:
                db.execute('DELETE FROM records WHERE collection=? AND id=? AND owner=?', (collection, identity, owner_id))

    def take(self, collection, identity, owner_id):
        """Atomically consume a one-use ticket, including across backend processes."""
        if self.gcs_bucket:
            from app.editor import gcs
            with self.lock:
                found = gcs.get_record(collection, owner_id, identity)
                if not found:
                    return None
                payload, revision, _gen = found
                gcs.delete_record(collection, owner_id, identity)
                return dict(payload, id=identity, revision=revision)
        if self.cloud:
            rows = self.request('DELETE', '/rest/v1/rayflow_records',
                                params={'collection': 'eq.' + collection, 'id': 'eq.' + identity, 'owner_id': 'eq.' + owner_id},
                                headers={'Prefer': 'return=representation'}).json()
            return dict(rows[0]['payload'], id=rows[0]['id'], revision=rows[0]['revision']) if rows else None
        with self.lock, self._db() as db:
            row = db.execute('DELETE FROM records WHERE collection=? AND id=? AND owner=? RETURNING *',
                             (collection, identity, owner_id)).fetchone()
            return dict(json.loads(row['payload']), id=row['id'], revision=row['revision']) if row else None

    def blob_path(self, owner_id, relative):
        return root_path() / 'workspaces' / owner_id / safe_relative(relative)

    def put_blob(self, owner_id, relative, content, content_type=None):
        relative = safe_relative(relative)
        if self.gcs_bucket:
            from app.editor import gcs
            gcs.upload_bytes(owner_id, relative, content,
                             content_type or mimetypes.guess_type(relative)[0] or 'application/octet-stream')
            # Also keep a local copy for same-request reads (e.g. FFmpeg access).
            path = self.blob_path(owner_id, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return path
        if self.cloud:
            self.request('POST', '/storage/v1/object/rayflow-private/' + quote(owner_id + '/' + relative, safe='/'), data=content,
                         headers={'Content-Type': content_type or mimetypes.guess_type(relative)[0] or 'application/octet-stream', 'x-upsert': 'true'})
        path = self.blob_path(owner_id, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.writing')
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def get_blob(self, owner_id, relative):
        path = self.blob_path(owner_id, relative)
        if path.is_file():
            return path
        if self.gcs_bucket:
            from app.editor import gcs
            path.parent.mkdir(parents=True, exist_ok=True)
            gcs.download_to(owner_id, safe_relative(relative), path)
            return path
        if not self.cloud:
            raise FileNotFoundError('Project file not found.')
        result = self.request('GET', '/storage/v1/object/authenticated/rayflow-private/' + quote(owner_id + '/' + safe_relative(relative), safe='/'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.content)
        return path

    def blob_size(self, owner_id, relative):
        local = self.blob_path(owner_id, relative)
        if local.is_file():
            return local.stat().st_size
        if self.gcs_bucket:
            from app.editor import gcs
            return gcs.object_size(owner_id, safe_relative(relative))
        if not self.cloud:
            return local.stat().st_size
        result = self.request('HEAD', '/storage/v1/object/authenticated/rayflow-private/' + quote(owner_id + '/' + safe_relative(relative), safe='/'))
        return int(result.headers.get('content-length', 0))

    def delete_blob(self, owner_id, relative):
        relative = safe_relative(relative)
        if self.gcs_bucket:
            from app.editor import gcs
            gcs.delete_object(owner_id, relative)
        if self.cloud:
            self.request('DELETE', '/storage/v1/object/rayflow-private', json={'prefixes': [owner_id + '/' + relative]})
        self.blob_path(owner_id, relative).unlink(missing_ok=True)

    def sign(self, owner_id, relative, upload=False):
        if self.gcs_bucket:
            from app.editor import gcs
            return gcs.signed_url(owner_id, safe_relative(relative), upload=upload)
        if not self.cloud:
            return None
        relative = safe_relative(relative)
        endpoint = '/storage/v1/object/upload/sign/' if upload else '/storage/v1/object/sign/'
        data = self.request('POST', endpoint + 'rayflow-private/' + quote(owner_id + '/' + relative, safe='/'),
                            json={} if upload else {'expiresIn': 900}).json()
        url = data.get('url') or data.get('signedURL') or data.get('signedUrl')
        if url and url.startswith('/'):
            url = os.environ['SUPABASE_URL'].rstrip('/') + ('' if url.startswith('/storage/v1/') else '/storage/v1') + url
        if not url:
            raise StorageUnavailable('Private storage did not return a signed URL.')
        return {'url': url, 'token': data.get('token'), 'path': owner_id + '/' + relative}


store = RecordStore()
