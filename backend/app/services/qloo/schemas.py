"""Normalized internal schemas for Qloo data.

These decouple RayFlow from Qloo's verbose response shapes. We keep a reference
back to the source Qloo entity/tag ID so downstream reasoning can be audited and
so we never conflate a user's declared preference with a Qloo-derived one.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# Qloo /v2/insights filter.type values supported for the hackathon.
SUPPORTED_ENTITY_TYPES = (
    'urn:entity:artist',
    'urn:entity:book',
    'urn:entity:brand',
    'urn:entity:destination',
    'urn:entity:movie',
    'urn:entity:person',
    'urn:entity:place',
    'urn:entity:podcast',
    'urn:entity:tv_show',
    'urn:entity:video_game',
)

# Friendly category -> Qloo entity type. Used to steer /search and /v2/insights.
CATEGORY_TO_ENTITY_TYPE = {
    'movie': 'urn:entity:movie',
    'director': 'urn:entity:person',
    'person': 'urn:entity:person',
    'artist': 'urn:entity:artist',
    'musician': 'urn:entity:artist',
    'band': 'urn:entity:artist',
    'tv_show': 'urn:entity:tv_show',
    'book': 'urn:entity:book',
    'brand': 'urn:entity:brand',
    'destination': 'urn:entity:destination',
    'place': 'urn:entity:place',
    'podcast': 'urn:entity:podcast',
    'video_game': 'urn:entity:video_game',
}


class ResolvedEntity(BaseModel):
    """A Qloo entity resolved from a user's declared preference."""
    qloo_id: str
    name: str
    entity_type: str  # Qloo URN, e.g. urn:entity:movie
    category: str      # friendly category the user entered under
    query: str         # the original user-entered text
    popularity: Optional[float] = None
    tags: List[str] = Field(default_factory=list)  # tag IDs attached by Qloo


class ResolvedTag(BaseModel):
    """A Qloo tag resolved from a user's interest/genre keyword."""
    tag_id: str
    name: str
    tag_type: Optional[str] = None
    query: str


class UnresolvedPreference(BaseModel):
    """A declared preference Qloo could not resolve to an entity or tag."""
    query: str
    category: str
    reason: str = 'No matching Qloo entity or tag was found.'


class CulturalAssociation(BaseModel):
    """A Qloo-derived association (NOT user-declared). Clearly labeled as inferred."""
    qloo_id: Optional[str] = None
    name: str
    entity_type: Optional[str] = None
    affinity: Optional[float] = None
    source: str = 'qloo_insights'
    # The declared entities that seeded this association, for auditability.
    derived_from: List[str] = Field(default_factory=list)


class TagSignal(BaseModel):
    """A tag with an affinity score aggregated from Qloo insights."""
    tag_id: str
    name: str
    affinity: Optional[float] = None
    weight: float = 1.0
