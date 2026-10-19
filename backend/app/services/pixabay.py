"""Bounded Pixabay searches and on-selection downloads. Credentials stay here."""
import hashlib
import json
import math
import os
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image
from app.core.config import CACHE_DIR, UPLOAD_DIR
from app.services.media import probe_media

CACHE = CACHE_DIR / 'pixabay'
CACHE.mkdir(parents=True, exist_ok=True)
TTL = 86400
_lock = threading.RLock()
_requests = deque()
_blocked_until = 0.0

class MediaProviderError(ValueError):
    pass

def _safe_url(value):
    parsed = urlparse(str(value))
    if (parsed.scheme != 'https' or parsed.hostname not in ('pixabay.com', 'cdn.pixabay.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise MediaProviderError('Pixabay returned an unsupported media address.')
    return str(value)

def _save(path, data):
    if _read(path) == data:
        return
    temp = path.with_suffix('.' + uuid.uuid4().hex + '.part')
    try:
        temp.write_text(json.dumps(data), encoding='utf-8')
        for attempt in range(4):
            try:
                temp.replace(path)
                break
            except PermissionError:
                if attempt == 3:
                    # OneDrive/antivirus may temporarily hold a cache file open.
                    # A provider cache write failure must not destroy the edit.
                    if path.exists():return
                    raise MediaProviderError('The media cache is temporarily locked. Please retry.') from None
                time.sleep(.05 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)

def _read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None

def _api(params, kind):
    global _blocked_until
    key = os.environ.get('PIXABAY_API_KEY', '').strip()
    if not key:
        raise MediaProviderError('Set PIXABAY_API_KEY in backend/.env and restart the backend to enable B-roll search.')
    cache_id = hashlib.sha256(json.dumps([kind, params], sort_keys=True).encode()).hexdigest()
    path = CACHE / f'search_{cache_id}.json'
    with _lock:
        saved = _read(path)
        if saved and time.time() - saved['created'] < TTL:
            return saved['data']
        now = time.time()
        while _requests and now - _requests[0] > 60:
            _requests.popleft()
        if now < _blocked_until or len(_requests) >= 85:
            raise MediaProviderError('Pixabay is rate-limited. Cached results remain available; try again in a minute.')
        _requests.append(now)
        url = 'https://pixabay.com/api/' + ('videos/' if kind == 'video' else '')
        try:
            response = requests.get(url, params={**params, 'key': key}, timeout=(5, 15), allow_redirects=False)
        except requests.RequestException:
            # Exceptions can contain the credential-bearing URL. Never propagate them.
            raise MediaProviderError('Pixabay could not be reached. Editing and export remain available.') from None
        try:
            if response.status_code == 429:
                retry = response.headers.get('Retry-After', response.headers.get('X-RateLimit-Reset', '60'))
                _blocked_until = now + min(3600, max(60, int(retry) if str(retry).isdigit() else 60))
                raise MediaProviderError('Pixabay rate limit reached. Please retry after the cooldown.')
            if response.status_code in (400, 401, 403):
                raise MediaProviderError('Pixabay rejected the request. Check PIXABAY_API_KEY in backend/.env.')
            if response.status_code != 200:
                raise MediaProviderError('Pixabay is temporarily unavailable.')
            try:
                data = response.json()
            except ValueError:
                raise MediaProviderError('Pixabay returned an unreadable response.') from None
            if not isinstance(data, dict) or not isinstance(data.get('hits'), list):
                raise MediaProviderError('Pixabay returned an unexpected response.')
            # Retain only needed provider fields; never store request URLs/headers.
            normalized = []
            for hit in data['hits'][:20]:
                try:
                    normalized.append(_normalize(hit, kind))
                except (ValueError, TypeError, KeyError):
                    continue
            _save(path, {'created': now, 'data': normalized})
            return normalized
        finally:
            response.close()

def _normalize(hit, kind):
    if kind == 'video':
        variants = hit.get('videos', {})
        variant = next((variants[name] for name in ('large', 'medium', 'small')
                        if variants.get(name, {}).get('url') and variants[name].get('size', 0) <= 120 * 1024**2), None)
        if not variant:
            raise ValueError('No usable video')
        url = variant['url']
        width, height = int(variant['width']), int(variant['height'])
        preview = variant.get('thumbnail') or ''
    else:
        url = hit.get('largeImageURL') or hit['webformatURL']
        width, height = int(hit['imageWidth']), int(hit['imageHeight'])
        preview = hit.get('webformatURL') or hit['previewURL']
    return {'id': int(hit['id']), 'media_type': kind, 'tags': str(hit.get('tags', ''))[:500],
            'width': width, 'height': height, 'duration': float(hit.get('duration', 0)),
            'source_page': _safe_url(hit['pageURL']), 'contributor': str(hit.get('user', ''))[:100],
            'preview_url': _safe_url(preview) if preview else '', '_download_url': _safe_url(url)}

def search(query, kind='image', aspect_ratio='9:16', duration=2.5):
    query = ' '.join(query.strip().split())[:100]
    if not query or kind not in ('image', 'video'):
        raise MediaProviderError('Enter a search phrase and choose images or videos.')
    data = _api({'q': query, 'safesearch': 'true', 'per_page': 20}, kind)
    keywords = {token.rstrip('s') for token in re.findall(r'[a-z0-9]+', query.lower())}
    target = {'9:16': 9/16, '16:9': 16/9, '1:1': 1}[aspect_ratio]
    results = []
    for asset in data:
        tags = {token.rstrip('s') for token in re.findall(r'[a-z0-9]+', asset['tags'].lower())}
        relevance = len(keywords & tags) / max(1, len(keywords))
        if 'biryani' in keywords and 'biryani' not in tags:
            relevance = 0
        # Relevance dominates geometry; no semantic match is never auto-selected.
        geometry = math.exp(-abs(math.log(max(.01, asset['width']/max(1, asset['height'])) / target)))
        quality = min(1, min(asset['width'], asset['height']) / 1080)
        length = 1 if kind == 'image' or asset['duration'] >= duration else .25
        item = {k: v for k, v in asset.items() if not k.startswith('_')}
        item.update(relevance=round(relevance, 3), score=round(relevance * 10 + geometry + quality + length, 3))
        results.append(item)
        asset_record = CACHE / f'asset_{kind}_{asset["id"]}.json'
        existing = _read(asset_record)
        if not existing or existing['data'] != asset:
            _save(asset_record, {'created': time.time(), 'data': asset})
    return sorted(results, key=lambda row: row['score'], reverse=True)

def download(asset_id, kind):
    if kind not in ('image', 'video') or not isinstance(asset_id, int) or asset_id <= 0:
        raise MediaProviderError('Invalid Pixabay asset selection.')
    with _lock:
        record_path = CACHE / f'asset_{kind}_{asset_id}.json'
        record = _read(record_path)
        if not record:
            raise MediaProviderError('Search for this asset before selecting it.')
        asset = record['data']
        suffix = '.mp4' if kind == 'video' else '.jpg'
        dest = UPLOAD_DIR / f'pixabay_{kind}_{asset_id}{suffix}'
        if dest.is_file():
            return {**{k: v for k, v in asset.items() if not k.startswith('_')}, 'url': f'/api/uploads/{dest.name}'}
        if time.time() - record['created'] >= TTL:
            fresh = _api({'id': asset_id, 'per_page': 3}, kind)
            asset = next((item for item in fresh if item['id'] == asset_id), None)
            if not asset:
                raise MediaProviderError('This Pixabay asset is no longer available.')
        temp = dest.with_suffix('.' + uuid.uuid4().hex + '.part')
        limit = (120 if kind == 'video' else 30) * 1024**2
        response = None
        try:
            url = _safe_url(asset['_download_url'])
            for _ in range(4):
                response = requests.get(url, stream=True, timeout=(5, 20), allow_redirects=False)
                if response.status_code in (301, 302, 303, 307, 308):
                    url = _safe_url(response.headers.get('Location', ''))
                    response.close()
                    continue
                break
            if response.status_code != 200:
                raise MediaProviderError('The selected media could not be downloaded. Search again to refresh its link.')
            content_type = response.headers.get('Content-Type', '').split(';')[0]
            allowed = ('video/mp4', 'application/octet-stream') if kind == 'video' else ('image/jpeg', 'image/png', 'image/webp', 'application/octet-stream')
            if content_type not in allowed:
                raise MediaProviderError('The provider returned an unsupported media type.')
            total = 0
            with temp.open('wb') as output:
                for chunk in response.iter_content(65536):
                    total += len(chunk)
                    if total > limit:
                        raise MediaProviderError('The selected media exceeds the download size limit.')
                    output.write(chunk)
            if kind == 'image':
                with Image.open(temp) as picture:
                    if picture.width * picture.height > 40_000_000:
                        raise MediaProviderError('The selected image is too large.')
                    picture.convert('RGB').save(temp, format='JPEG', quality=95)
            else:
                info = probe_media(temp)
                if not info['has_video'] or info['duration'] <= 0:
                    raise MediaProviderError('The selected video could not be decoded.')
            temp.replace(dest)
            _save(record_path, {'created': time.time(), 'data': asset})
            return {**{k: v for k, v in asset.items() if not k.startswith('_')}, 'url': f'/api/uploads/{dest.name}'}
        except requests.RequestException:
            raise MediaProviderError('Media download interrupted. Please retry.') from None
        finally:
            if response is not None:
                response.close()
            temp.unlink(missing_ok=True)
