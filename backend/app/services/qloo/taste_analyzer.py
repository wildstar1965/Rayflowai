"""Retrieve cultural intelligence from Qloo Insights.

Given resolved entity IDs and tag IDs, we query GET /v2/insights for one or more
``filter.type`` categories, passing the user's entities/tags as signals:

    signal.interests.entities = <comma-separated entity IDs>
    signal.interests.tags     = <comma-separated tag IDs>

We aggregate the returned entities into ``CulturalAssociation`` records and the
returned/queried tags into ``TagSignal`` records. Empty results are expected for
some entities in the hackathon dataset and are handled gracefully.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.services.qloo.cache import cached
from app.services.qloo.client import QlooClient, QlooError
from app.services.qloo.schemas import (
    CulturalAssociation,
    ResolvedEntity,
    ResolvedTag,
    TagSignal,
)

logger = logging.getLogger('rayflow.qloo')

# The entity categories we ask Qloo to illuminate from the user's signals. We
# keep this focused on culturally expressive categories relevant to editing
# aesthetics (film, music, people). All are supported hackathon filter.types.
INSIGHT_TARGET_TYPES = (
    'urn:entity:movie',
    'urn:entity:artist',
)

MAX_SIGNAL_ENTITIES = 10
MAX_TAKE = 15


class TasteInsights:
    """Container for aggregated Qloo-derived cultural intelligence."""

    def __init__(self):
        self.associations: List[CulturalAssociation] = []
        self._association_keys: set = set()
        self.tag_signals: Dict[str, TagSignal] = {}
        self.queried_types: List[str] = []
        self.notes: List[str] = []

    def add_association(self, association: CulturalAssociation) -> None:
        # Dedupe by Qloo ID (or name+type when no ID), keeping the higher affinity.
        key = association.qloo_id or f'{association.name}|{association.entity_type}'
        if key in self._association_keys:
            for existing in self.associations:
                existing_key = existing.qloo_id or f'{existing.name}|{existing.entity_type}'
                if existing_key == key:
                    if (association.affinity or 0) > (existing.affinity or 0):
                        existing.affinity = association.affinity
                    for seed in association.derived_from:
                        if seed not in existing.derived_from:
                            existing.derived_from.append(seed)
                    break
            return
        self._association_keys.add(key)
        self.associations.append(association)

    def add_tag(self, tag_id: str, name: str, affinity: Optional[float], weight: float = 1.0):
        existing = self.tag_signals.get(tag_id)
        if existing:
            existing.weight += weight
            if affinity is not None:
                existing.affinity = max(existing.affinity or 0.0, affinity)
        else:
            self.tag_signals[tag_id] = TagSignal(
                tag_id=tag_id, name=name, affinity=affinity, weight=weight)

    def to_dict(self) -> dict:
        return {
            'associations': [a.model_dump() for a in self.associations],
            'tag_signals': [t.model_dump() for t in sorted(
                self.tag_signals.values(),
                key=lambda t: (t.affinity or 0, t.weight), reverse=True)],
            'queried_types': self.queried_types,
            'notes': self.notes,
        }


def analyze_taste(
    entities: List[ResolvedEntity],
    tags: List[ResolvedTag],
    client: Optional[QlooClient] = None,
    target_types: tuple = INSIGHT_TARGET_TYPES,
) -> TasteInsights:
    """Query Qloo Insights using the user's resolved entities/tags as signals."""
    client = client or QlooClient()
    insights = TasteInsights()

    entity_ids = [e.qloo_id for e in entities if e.qloo_id][:MAX_SIGNAL_ENTITIES]
    tag_ids = [t.tag_id for t in tags if t.tag_id]

    # Seed tag signals from the user's own declared genre/interest tags.
    for tag in tags:
        insights.add_tag(tag.tag_id, tag.name, affinity=None, weight=1.0)

    if not entity_ids and not tag_ids:
        insights.notes.append('No resolvable Qloo signals were available.')
        return insights

    base_signal: Dict[str, str] = {}
    if entity_ids:
        base_signal['signal.interests.entities'] = ','.join(entity_ids)
    if tag_ids:
        base_signal['signal.interests.tags'] = ','.join(tag_ids)

    for entity_type in target_types:
        params = {**base_signal, 'filter.type': entity_type, 'take': MAX_TAKE}
        try:
            data = cached('insights', params, lambda p=params: client.insights(p))
        except QlooError as exc:
            # 403 = this type isn't permitted for the key; skip it, don't fail.
            logger.info('Qloo insights for %s failed: %s', entity_type, exc)
            if exc.status == 403:
                insights.notes.append(f'{entity_type} is not available for this key.')
                continue
            raise
        insights.queried_types.append(entity_type)
        _ingest(insights, data, entity_type, entity_ids)

    if not insights.associations and not insights.tag_signals:
        insights.notes.append('Qloo returned no cultural associations for these inputs.')
    return insights


def _ingest(insights: TasteInsights, data: dict, entity_type: str, derived_from: List[str]) -> None:
    from app.services.qloo.client import _results_list
    for item in _results_list(data):
        name = str(item.get('name') or item.get('title') or '').strip()
        if not name:
            continue
        qloo_id = str(item.get('entity_id') or item.get('id') or '').strip() or None
        affinity = _affinity(item)
        insights.add_association(CulturalAssociation(
            qloo_id=qloo_id,
            name=name,
            entity_type=entity_type,
            affinity=affinity,
            derived_from=list(derived_from),
        ))
        # Harvest tags attached to each association as weighted signals.
        for tag in _item_tags(item):
            tag_id = str(tag.get('tag_id') or tag.get('id') or '').strip()
            tag_name = str(tag.get('name') or '').strip()
            if tag_id and tag_name:
                insights.add_tag(tag_id, tag_name, affinity, weight=0.5)


def _affinity(item: dict) -> Optional[float]:
    for key in ('affinity', 'score', 'popularity'):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    query = item.get('query')
    if isinstance(query, dict):
        for key in ('affinity', 'measurements'):
            value = query.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _item_tags(item: dict) -> List[dict]:
    tags = item.get('tags')
    if isinstance(tags, list):
        return [t for t in tags if isinstance(t, dict)]
    properties = item.get('properties')
    if isinstance(properties, dict) and isinstance(properties.get('tags'), list):
        return [t for t in properties['tags'] if isinstance(t, dict)]
    return []
