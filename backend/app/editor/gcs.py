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
