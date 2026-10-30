"""Build a normalized Taste Profile from resolved Qloo data.

The profile is the single source of truth persisted per workspace and fed to the
Taste Intelligence agent. It is deliberately structured to keep three layers
clearly separated and auditable:

  * ``declared``   - exactly what the user entered (never inferred).
  * ``resolved``   - the Qloo entities/tags we matched those inputs to.
  * ``cultural``   - Qloo-DERIVED associations and tag signals (inferred, labeled).

No AI interpretation happens here; that is the agent's job. This keeps "what the
user said" strictly distinct from "what Qloo inferred" and "what the AI decided".
"""
from __future__ import annotations

import time
from typing import List, Optional

from pydantic import BaseModel, Field

from app.services.qloo.client import QlooClient
from app.services.qloo.entity_resolver import resolve_entities
from app.services.qloo.schemas import (
    CulturalAssociation,
    ResolvedEntity,
    ResolvedTag,
    TagSignal,
    UnresolvedPreference,
)
from app.services.qloo.taste_analyzer import analyze_taste

PROFILE_VERSION = 1


class DeclaredPreference(BaseModel):
    text: str
    category: str


class TasteProfile(BaseModel):
    """The persisted, normalized taste profile for a workspace."""
    version: int = PROFILE_VERSION
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    source: str = 'qloo'  # 'qloo' when Qloo data was used, 'declared_only' otherwise.

    declared: List[DeclaredPreference] = Field(default_factory=list)
    resolved_entities: List[ResolvedEntity] = Field(default_factory=list)
    resolved_tags: List[ResolvedTag] = Field(default_factory=list)
    unresolved: List[UnresolvedPreference] = Field(default_factory=list)

    cultural_associations: List[CulturalAssociation] = Field(default_factory=list)
    tag_signals: List[TagSignal] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    def summary(self) -> dict:
        """A compact, LLM-friendly summary used as agent context. Contains only
        Qloo IDs/names and affinities - never any user media."""
        return {
            'declared': [d.model_dump() for d in self.declared],
            'resolved_entities': [
                {'name': e.name, 'type': e.entity_type, 'category': e.category}
                for e in self.resolved_entities
            ],
            'cultural_associations': [
                {'name': a.name, 'type': a.entity_type, 'affinity': a.affinity}
                for a in sorted(self.cultural_associations,
                                key=lambda a: a.affinity or 0, reverse=True)[:20]
            ],
            'tag_signals': [
                {'name': t.name, 'affinity': t.affinity, 'weight': t.weight}
                for t in sorted(self.tag_signals,
                                key=lambda t: (t.affinity or 0, t.weight), reverse=True)[:25]
            ],
            'notes': self.notes,
        }


def build_profile(
    preferences: List[dict],
    client: Optional[QlooClient] = None,
    use_qloo: bool = True,
) -> TasteProfile:
    """Resolve preferences through Qloo and assemble a taste profile.

    When ``use_qloo`` is False (or Qloo is unconfigured and the caller opts out),
    a declared-only profile is returned so the feature degrades gracefully.
    """
    declared = [
        DeclaredPreference(text=str(p.get('text', '')).strip(),
                           category=str(p.get('category', 'movie')).strip().lower())
        for p in preferences if str(p.get('text', '')).strip()
    ]

    if not use_qloo:
        return TasteProfile(declared=declared, source='declared_only',
                            notes=['Qloo analysis was skipped; profile reflects declared preferences only.'])

    client = client or QlooClient()
    entities, tags, unresolved = resolve_entities([d.model_dump() for d in declared], client=client)
    insights = analyze_taste(entities, tags, client=client)

    return TasteProfile(
        declared=declared,
        resolved_entities=entities,
        resolved_tags=tags,
        unresolved=unresolved,
        cultural_associations=insights.associations,
        tag_signals=list(insights.tag_signals.values()),
        notes=insights.notes,
        source='qloo',
    )
