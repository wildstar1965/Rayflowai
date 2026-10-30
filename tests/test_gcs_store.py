"""Unit tests for the GCS records backend using an in-memory fake bucket.

Validates list/get/put/delete/take semantics and optimistic concurrency without
any real GCS or network.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


class FakeBlob:
    def __init__(self, bucket, name):
        self._bucket = bucket
        self.name = name

    @property
    def generation(self):
        entry = self._bucket.objects.get(self.name)
        return entry[1] if entry else None

    def download_as_bytes(self):
        entry = self._bucket.objects.get(self.name)
        if entry is None:
            raise FileNotFoundError(self.name)
        return entry[0]

    def upload_from_string(self, body, content_type=None, if_generation_match=None):
        from google.api_core.exceptions import PreconditionFailed
        current = self._bucket.objects.get(self.name)
        current_gen = current[1] if current else 0
        if if_generation_match is not None and if_generation_match != current_gen:
            raise PreconditionFailed('generation mismatch')
        data = body.encode() if isinstance(body, str) else body
        self._bucket.objects[self.name] = (data, (current_gen or 0) + 1)

    def delete(self):
        self._bucket.objects.pop(self.name, None)


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name):
        return FakeBlob(self, name)


class FakeClient:
    def __init__(self, bucket):
        self._bucket = bucket

    def list_blobs(self, bucket, prefix=''):
        return [FakeBlob(bucket, name) for name in sorted(bucket.objects) if name.startswith(prefix)]


@pytest.fixture
def gcs_store(monkeypatch):
    # google.api_core may not be installed offline; provide a stub exception.
    try:
        import google.api_core.exceptions  # noqa: F401
    except Exception:
        import types
        mod = types.ModuleType('google.api_core.exceptions')
        class PreconditionFailed(Exception):
            pass
        mod.PreconditionFailed = PreconditionFailed
        sys.modules['google.api_core.exceptions'] = mod
        sys.modules.setdefault('google', types.ModuleType('google'))
        sys.modules.setdefault('google.api_core', types.ModuleType('google.api_core'))

    from app.editor import gcs
    bucket = FakeBucket()
    monkeypatch.setenv('GCS_BUCKET', 'test-bucket')
    monkeypatch.setattr(gcs, '_bucket', lambda: bucket)
    monkeypatch.setattr(gcs, '_client', lambda: FakeClient(bucket))
    monkeypatch.setattr(gcs, '_object_name', lambda o, r: f'{o}/{r}')
    from app.editor.store import RecordStore
    return RecordStore(), gcs


def test_gcs_put_get_list_delete(gcs_store):
    store, _ = gcs_store
    store.put('projects', 'p1', 'ws1', {'name': 'Reel'})
    got = store.get('projects', 'p1', 'ws1')
    assert got['name'] == 'Reel' and got['revision'] == 1
    store.put('projects', 'p2', 'ws1', {'name': 'Second'})
    listed = store.list('projects', 'ws1')
    assert {r['id'] for r in listed} == {'p1', 'p2'}
    store.delete('projects', 'p1', 'ws1')
    assert store.get('projects', 'p1', 'ws1') is None


def test_gcs_optimistic_concurrency(gcs_store):
    store, _ = gcs_store
    store.put('projects', 'p1', 'ws1', {'v': 1})
    # Correct expected revision succeeds and bumps revision.
    updated = store.put('projects', 'p1', 'ws1', {'v': 2}, expected=1)
    assert updated['revision'] == 2
    # Stale expected revision must conflict.
    from app.editor.store import Conflict
    with pytest.raises(Conflict):
        store.put('projects', 'p1', 'ws1', {'v': 3}, expected=1)


def test_gcs_workspace_isolation(gcs_store):
    store, _ = gcs_store
    store.put('taste_profiles', 'ws1', 'ws1', {'source': 'qloo'})
    store.put('taste_profiles', 'ws2', 'ws2', {'source': 'declared_only'})
    assert store.get('taste_profiles', 'ws1', 'ws1')['source'] == 'qloo'
    assert store.list('taste_profiles', 'ws2') == [
        {'source': 'declared_only', 'id': 'ws2', 'revision': 1}]
    assert store.get('taste_profiles', 'ws1', 'ws2') is None


def test_gcs_take_is_one_shot(gcs_store):
    store, _ = gcs_store
    store.put('tickets', 't1', 'ws1', {'use': 'once'})
    taken = store.take('tickets', 't1', 'ws1')
    assert taken['use'] == 'once'
    assert store.take('tickets', 't1', 'ws1') is None
