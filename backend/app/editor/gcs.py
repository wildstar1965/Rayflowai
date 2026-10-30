"""Google Cloud Storage blob backend for Cloud Run deployments.

Cloud Run instances have an ephemeral filesystem, so persistent user media,
project assets, and rendered exports must live in GCS. This module is a thin,
lazily-imported wrapper around the official ``google-cloud-storage`` client so
the dependency is only required when ``GCS_BUCKET`` is configured.

Objects are laid out as ``<workspace_id>/<relative_path>`` inside the bucket,
mirroring the local/Supabase layout. The bucket must be private; downloads are
served by the backend or via short-lived signed URLs.
"""
from __future__ import annotations

import functools
import os
from typing import Optional


class GcsUnavailable(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def _client():
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:  # pragma: no cover - only hit without the dep
        raise GcsUnavailable(
            'google-cloud-storage is not installed. Add it to requirements to use GCS.') from exc
    return storage.Client()


@functools.lru_cache(maxsize=1)
def _bucket():
    name = os.getenv('GCS_BUCKET', '').strip()
    if not name:
        raise GcsUnavailable('GCS_BUCKET is not configured.')
    return _client().bucket(name)


def _object_name(owner_id: str, relative: str) -> str:
    prefix = os.getenv('GCS_PREFIX', '').strip('/')
    key = f'{owner_id}/{relative}'
    return f'{prefix}/{key}' if prefix else key


def upload_bytes(owner_id: str, relative: str, content: bytes, content_type: Optional[str] = None) -> None:
    blob = _bucket().blob(_object_name(owner_id, relative))
    blob.upload_from_string(content, content_type=content_type or 'application/octet-stream')


def download_to(owner_id: str, relative: str, destination) -> None:
    blob = _bucket().blob(_object_name(owner_id, relative))
    if not blob.exists():
        raise FileNotFoundError('Project file not found in GCS.')
    blob.download_to_filename(str(destination))


def object_size(owner_id: str, relative: str) -> int:
    blob = _bucket().blob(_object_name(owner_id, relative))
    blob.reload()
    return int(blob.size or 0)


def delete_object(owner_id: str, relative: str) -> None:
    blob = _bucket().blob(_object_name(owner_id, relative))
    try:
        blob.delete()
    except Exception:
        # Deleting a missing object must not raise (idempotent cleanup).
        pass


def signed_url(owner_id: str, relative: str, *, upload: bool = False, expires_seconds: int = 900) -> dict:
    from datetime import timedelta
    blob = _bucket().blob(_object_name(owner_id, relative))
    method = 'PUT' if upload else 'GET'
    url = blob.generate_signed_url(version='v4', expiration=timedelta(seconds=expires_seconds), method=method)
    return {'url': url, 'token': None, 'path': _object_name(owner_id, relative)}


# ---------------------------------------------------------------------------
# Record persistence in GCS (replaces the need for Supabase / Cloud SQL).
#
# Records are stored as individual JSON objects so there is no external
# database to provision. Layout inside the bucket:
#
#   [<prefix>/]records/<collection>/<owner_id>/<id>.json
#
# Each object stores {payload, revision, updated}. Optimistic concurrency uses
# the GCS object generation precondition (if_generation_match), which gives us
# atomic compare-and-set without any extra service.
# ---------------------------------------------------------------------------
import json as _json


def _record_name(collection: str, owner_id: str, identity: str) -> str:
    prefix = os.getenv('GCS_PREFIX', '').strip('/')
    key = f'records/{collection}/{owner_id}/{identity}.json'
    return f'{prefix}/{key}' if prefix else key


def _record_folder(collection: str, owner_id: str) -> str:
    prefix = os.getenv('GCS_PREFIX', '').strip('/')
    key = f'records/{collection}/{owner_id}/'
    return f'{prefix}/{key}' if prefix else key


def get_record(collection: str, owner_id: str, identity: str):
    """Return (payload_dict, revision, generation) or None."""
    blob = _bucket().blob(_record_name(collection, owner_id, identity))
    try:
        data = blob.download_as_bytes()
    except Exception:
        return None
    try:
        stored = _json.loads(data)
    except ValueError:
        return None
    return stored.get('payload', {}), int(stored.get('revision', 0)), blob.generation


def list_records(collection: str, owner_id: str):
    """Return a list of (identity, payload, revision), newest first."""
    bucket = _bucket()
    folder = _record_folder(collection, owner_id)
    out = []
    for blob in _client().list_blobs(bucket, prefix=folder):
        if not blob.name.endswith('.json'):
            continue
        try:
            stored = _json.loads(blob.download_as_bytes())
        except Exception:
            continue
        identity = blob.name.rsplit('/', 1)[-1][:-5]  # strip ".json"
        out.append((identity, stored.get('payload', {}), int(stored.get('revision', 0)),
                    float(stored.get('updated', 0))))
    out.sort(key=lambda row: row[3], reverse=True)
    return [(identity, payload, revision) for identity, payload, revision, _ in out]


def put_record(collection: str, owner_id: str, identity: str, payload: dict,
               revision: int, *, expected_generation=None) -> bool:
    """Write a record with an optimistic-concurrency precondition.

    ``expected_generation`` is the GCS object generation the caller observed
    (0 means "must not already exist"). Returns False on a precondition failure
    (someone else changed it), True on success.
    """
    import time as _time
    blob = _bucket().blob(_record_name(collection, owner_id, identity))
    body = _json.dumps({'payload': payload, 'revision': revision, 'updated': _time.time()})
    kwargs = {'content_type': 'application/json'}
    if expected_generation is not None:
        kwargs['if_generation_match'] = expected_generation
    try:
        from google.api_core.exceptions import PreconditionFailed  # type: ignore
    except ImportError:  # pragma: no cover
        PreconditionFailed = ()  # type: ignore
    try:
        blob.upload_from_string(body, **kwargs)
        return True
    except Exception as exc:  # noqa: BLE001
        if PreconditionFailed and isinstance(exc, PreconditionFailed):
            return False
        raise


def delete_record(collection: str, owner_id: str, identity: str):
    blob = _bucket().blob(_record_name(collection, owner_id, identity))
    try:
        blob.delete()
    except Exception:
        pass
