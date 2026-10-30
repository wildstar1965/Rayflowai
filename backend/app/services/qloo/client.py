"""Secure, server-only transport for the Qloo hackathon API.

Design notes:
- The API key is read from backend settings/env via ``setting('QLOO_API_KEY')``
  and sent only in the ``X-Api-Key`` header, never as a query parameter and
  never returned to the browser.
- Only the documented hackathon endpoints are used: ``/search``, ``/v2/insights``
  and ``/v2/tags``. ``/v2/insights`` is a GET request with query-string params.
- Qloo silently ignores unsupported params and may return an empty ``results``
  array; callers must treat empty results as "no data", not an error.
- Transient failures (timeouts, 429, 5xx) are retried with capped backoff.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

from app.services.provider_settings import setting

logger = logging.getLogger('rayflow.qloo')

# Hackathon keys are ONLY valid against this base URL. The staging/production
# hosts return 401 even with a valid hackathon key, so we pin the default and
# allow an operator override for non-hackathon environments.
DEFAULT_BASE_URL = 'https://hackathon.api.qloo.com'

# Connect/read timeouts (seconds). Qloo insight calls can be slower than search.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20

# Retry policy for transient errors only.
MAX_RETRIES = 3
BACKOFF_BASE = 0.5  # seconds; grows as BACKOFF_BASE * 2**attempt, capped.
BACKOFF_CAP = 4.0

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class QlooError(RuntimeError):
    """A Qloo request failed in a way the caller should surface to the user."""

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class QlooConfigError(QlooError):
    """Qloo is not configured (missing API key)."""


def qloo_base_url() -> str:
    """Return the configured Qloo base URL, defaulting to the hackathon host."""
    value = (setting('QLOO_BASE_URL', '') or DEFAULT_BASE_URL).strip().rstrip('/')
    if not value.startswith('https://'):
        # Never allow a plaintext endpoint for credentialed requests.
        raise QlooConfigError('QLOO_BASE_URL must be an HTTPS URL.')
    return value


def qloo_configured() -> bool:
    """True when a Qloo API key is available, without revealing it."""
    return bool(setting('QLOO_API_KEY', '').strip())


class QlooClient:
    """Thin, resilient HTTP client for the Qloo hackathon API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 session: Optional[requests.Session] = None):
        self._api_key = (api_key if api_key is not None else setting('QLOO_API_KEY', '')).strip()
        self._base_url = (base_url or qloo_base_url()).rstrip('/')
        self._session = session or requests.Session()

    # -- public API ---------------------------------------------------------

    def search(self, query: str, *, types: Optional[str] = None,
               take: int = 5, extra: Optional[Dict[str, Any]] = None) -> list[dict]:
        """Resolve a free-text name to Qloo entities via GET /search.

        ``types`` is the Qloo /search ``types`` filter (comma-separated URNs such
        as ``urn:entity:movie``). Returns the normalized ``results`` list.
        """
        if not query or not query.strip():
            return []
        params: Dict[str, Any] = {'query': query.strip(), 'take': max(1, min(int(take), 20))}
        if types:
            params['types'] = types
        if extra:
            params.update(extra)
        data = self._get('/search', params)
        return _results_list(data)

    def tags_search(self, query: str, *, take: int = 10,
                    extra: Optional[Dict[str, Any]] = None) -> list[dict]:
        """Find valid tag IDs by keyword via GET /v2/tags."""
        if not query or not query.strip():
            return []
        params: Dict[str, Any] = {'filter.query': query.strip(), 'take': max(1, min(int(take), 50))}
        if extra:
            params.update(extra)
        data = self._get('/v2/tags', params)
        return _results_list(data)

    def insights(self, params: Dict[str, Any]) -> dict:
        """Call GET /v2/insights. ``params`` must include ``filter.type``.

        Returns the raw-but-validated JSON body (a dict). An empty entities list
        is a valid, non-error outcome.
        """
        if not params.get('filter.type'):
            raise QlooError('Insights requires a filter.type (e.g. urn:entity:movie).')
        return self._get('/v2/insights', params)

    # -- internals ----------------------------------------------------------

    def _get(self, path: str, params: Dict[str, Any]) -> dict:
        if not self._api_key:
            raise QlooConfigError('Qloo is not configured. Add QLOO_API_KEY on the backend.')
        url = self._base_url + path
        headers = {'X-Api-Key': self._api_key, 'Accept': 'application/json'}
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._session.get(
                    url, headers=headers, params=params,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False,
                )
            except requests.Timeout:
                last_exc = QlooError('Qloo timed out. Please retry.')
                self._sleep(attempt)
                continue
            except requests.RequestException:
                last_exc = QlooError('Qloo could not be reached. Check network access and retry.')
                self._sleep(attempt)
                continue

            status = response.status_code
            if status in RETRYABLE_STATUS and attempt < MAX_RETRIES - 1:
                # Honor Retry-After when present (seconds form).
                self._sleep(attempt, response.headers.get('Retry-After'))
                continue
            return self._handle(status, response, path)
        # Exhausted retries on a transient failure.
        raise last_exc or QlooError('Qloo is temporarily unavailable. Please retry.')

    def _handle(self, status: int, response: requests.Response, path: str) -> dict:
        if status == 401:
            # Do not echo the body; it can be misleading about key validity.
            raise QlooError(
                'Qloo rejected the API key. Confirm QLOO_API_KEY and that it targets '
                'hackathon.api.qloo.com.', status=401)
        if status == 403:
            raise QlooError(
                'Qloo denied access for this entity type or resource. Use a supported '
                'filter.type.', status=403)
        if status == 429:
            raise QlooError('Qloo rate or quota limit reached. Wait before retrying.', status=429)
        if status == 404:
            raise QlooError('Qloo endpoint not found. Check the request path.', status=404)
        if not 200 <= status < 300:
            logger.warning('Qloo %s returned HTTP %s', path, status)
            raise QlooError('Qloo is unavailable. Please try again later.', status=status)
        try:
            data = response.json()
        except ValueError:
            raise QlooError('Qloo returned a non-JSON response.', status=status) from None
        if not isinstance(data, dict):
            raise QlooError('Qloo returned an unexpected response shape.', status=status)
        return data

    @staticmethod
    def _sleep(attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(min(float(retry_after), BACKOFF_CAP))
                return
            except (TypeError, ValueError):
                pass
        time.sleep(min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP))


def _results_list(data: dict) -> list[dict]:
    """Extract the list of result objects from a Qloo response.

    Qloo responses vary slightly by endpoint; results may appear under
    ``results`` (a list) or ``results.entities`` / ``results.tags``. This
    normalizes all shapes to a plain list of dicts.
    """
    results = data.get('results')
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    if isinstance(results, dict):
        for key in ('entities', 'tags', 'items'):
            value = results.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    # Some endpoints place entities at the top level.
    for key in ('entities', 'tags'):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []
