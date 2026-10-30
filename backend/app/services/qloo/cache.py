"""Private, server-side cache for Qloo responses.

Qloo's hackathon terms allow private server-side caching with no time limit, as
long as cached data is not stored in a public repository. We cache in-process
with a bounded TTL + LRU eviction. Entity/tag resolutions and insight calls are
deterministic for a given input, so caching cuts latency and quota usage.

The cache lives only in process memory, so it is never committed anywhere.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional, TypeVar

T = TypeVar('T')

# Defaults chosen to be safe for a hackathon workload; tune via env if needed.
DEFAULT_TTL_SECONDS = 60 * 60 * 6  # 6 hours
DEFAULT_MAX_ENTRIES = 1024


class TTLCache:
    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS, max_entries: int = DEFAULT_MAX_ENTRIES):
        self.ttl = ttl
        self.max_entries = max_entries
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < time.monotonic():
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_cache = TTLCache()


def cache_key(namespace: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]
    return f'{namespace}:{digest}'


def cached(namespace: str, payload: Any, producer: Callable[[], T]) -> T:
    """Return a cached value for (namespace, payload) or compute and store it."""
    key = cache_key(namespace, payload)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    value = producer()
    # Only cache successful, non-empty-ish results to avoid pinning failures.
    if value is not None:
        _cache.set(key, value)
    return value


def clear_cache() -> None:
    """Testing/ops hook to flush the cache."""
    _cache.clear()
