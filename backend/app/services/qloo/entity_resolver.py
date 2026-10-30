"""Resolve user-declared preferences into Qloo entity and tag IDs.

The resolver maps a friendly category (movie, director, artist, genre, ...) to
the appropriate Qloo /search type, picks the best match, and normalizes it into
our internal ``ResolvedEntity`` / ``ResolvedTag`` schemas. Unresolvable inputs
are returned separately so the UI can be transparent about coverage.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.services.qloo.cache import cached
from app.services.qloo.client import QlooClient, QlooError
from app.services.qloo.schemas import (
    CATEGORY_TO_ENTITY_TYPE,
    ResolvedEntity,
    ResolvedTag,
    UnresolvedPreference,
)

logger = logging.getLogger('rayflow.qloo')

# Categories that should resolve to a Qloo *tag* (genre/interest/mood) rather
# than a concrete entity.
TAG_CATEGORIES = {'genre', 'music_genre', 'mood', 'interest', 'aesthetic', 'style'}


def _entity_name(item: dict) -> str:
    return str(item.get('name') or item.get('title') or '').strip()


def _entity_id(item: dict) -> str:
    return str(item.get('entity_id') or item.get('id') or item.get('qloo_id') or '').strip()


def _entity_type(item: dict, fallback: str) -> str:
    # Qloo entities expose their type either as a top-level field or nested.
    value = item.get('type') or item.get('entity_type')
    if isinstance(value, str) and value.startswith('urn:entity:'):
        return value
    types = item.get('types')
    if isinstance(types, list):
        for candidate in types:
            if isinstance(candidate, str) and candidate.startswith('urn:entity:'):
                return candidate
    return fallback


def _popularity(item: dict) -> Optional[float]:
    for key in ('popularity', 'score', 'affinity'):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    properties = item.get('properties')
    if isinstance(properties, dict) and isinstance(properties.get('popularity'), (int, float)):
        return float(properties['popularity'])
    return None


def _tag_ids(item: dict) -> List[str]:
    tags = item.get('tags')
    ids: List[str] = []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                tag_id = tag.get('tag_id') or tag.get('id')
                if tag_id:
                    ids.append(str(tag_id))
    return ids


def resolve_entities(
    preferences: List[dict],
    client: Optional[QlooClient] = None,
) -> Tuple[List[ResolvedEntity], List[ResolvedTag], List[UnresolvedPreference]]:
    """Resolve a list of {text, category} preferences.

    Returns (entities, tags, unresolved). Entity-type categories resolve via
    /search; genre/interest/mood categories resolve via /v2/tags.
    """
    client = client or QlooClient()
    entities: List[ResolvedEntity] = []
    tags: List[ResolvedTag] = []
    unresolved: List[UnresolvedPreference] = []

    for pref in preferences:
        text = str(pref.get('text', '')).strip()
        category = str(pref.get('category', '')).strip().lower() or 'movie'
        if not text:
            continue
        try:
            if category in TAG_CATEGORIES:
                tag = _resolve_one_tag(client, text, category)
                if tag:
                    tags.append(tag)
                else:
                    unresolved.append(UnresolvedPreference(query=text, category=category))
            else:
                entity = _resolve_one_entity(client, text, category)
                if entity:
                    entities.append(entity)
                else:
                    unresolved.append(UnresolvedPreference(query=text, category=category))
        except QlooError as exc:
            logger.info('Qloo resolution failed for %r (%s): %s', text, category, exc)
            unresolved.append(UnresolvedPreference(
                query=text, category=category, reason='Qloo could not be reached for this item.'))
    return entities, tags, unresolved


def _resolve_one_entity(client: QlooClient, text: str, category: str) -> Optional[ResolvedEntity]:
    entity_type = CATEGORY_TO_ENTITY_TYPE.get(category, 'urn:entity:movie')

    def produce():
        return client.search(text, types=entity_type, take=5)

    results = cached('search', {'q': text, 'type': entity_type}, produce)
    best = _best_match(results, text)
    if not best:
        # Retry without a type filter in case the category guess was wrong.
        results = cached('search', {'q': text, 'type': 'any'}, lambda: client.search(text, take=5))
        best = _best_match(results, text)
        if not best:
            return None
    return ResolvedEntity(
        qloo_id=_entity_id(best),
        name=_entity_name(best) or text,
        entity_type=_entity_type(best, entity_type),
        category=category,
        query=text,
        popularity=_popularity(best),
        tags=_tag_ids(best),
    )


def _resolve_one_tag(client: QlooClient, text: str, category: str) -> Optional[ResolvedTag]:
    def produce():
        return client.tags_search(text, take=10)

    results = cached('tags', {'q': text}, produce)
    best = _best_match(results, text)
    if not best:
        return None
    tag_id = best.get('tag_id') or best.get('id')
    if not tag_id:
        return None
    return ResolvedTag(
        tag_id=str(tag_id),
        name=str(best.get('name') or text),
        tag_type=best.get('type') or best.get('subtype'),
        query=text,
    )


def _best_match(results: List[dict], text: str) -> Optional[dict]:
    """Pick the best result: exact (case-insensitive) name match wins, else the
    first result with a usable ID (Qloo orders by relevance)."""
    if not results:
        return None
    lowered = text.strip().lower()
    for item in results:
        if _entity_name(item).lower() == lowered and (_entity_id(item) or item.get('tag_id') or item.get('id')):
            return item
    for item in results:
        if _entity_id(item) or item.get('tag_id') or item.get('id'):
            return item
    return None


def resolve_tags(keywords: List[str], client: Optional[QlooClient] = None) -> List[ResolvedTag]:
    """Convenience: resolve a flat list of genre/interest keywords to tags."""
    client = client or QlooClient()
    tags: List[ResolvedTag] = []
    for keyword in keywords:
        text = str(keyword).strip()
        if not text:
            continue
        try:
            tag = _resolve_one_tag(client, text, 'genre')
            if tag:
                tags.append(tag)
        except QlooError:
            continue
    return tags
