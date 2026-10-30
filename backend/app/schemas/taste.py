"""Pydantic schemas for the Taste Intelligence layer.

These validate the LLM's output BEFORE it is allowed to touch the editing
engine. Every field is constrained to values the RayFlow renderer actually
supports, so an agent can never produce an unsupported or arbitrary operation.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Allowed values mirror EditingPlan and REEL_STYLES exactly.
ASPECT_RATIOS = ('9:16', '16:9', '1:1')
PACINGS = ('slow', 'balanced', 'fast', 'beat_driven')
STYLES = ('cinematic', 'vintage', 'noir', 'vibrant', 'minimal')
MOTIONS = ('slow_zoom', 'dynamic', 'static')
TRANSITIONS = ('none', 'crossfade', 'dip_black', 'dip_white', 'fade')
CLIP_MOTIONS = ('zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'static')


class StrategyReason(BaseModel):
    """One auditable decision tying an editing choice to a cultural basis."""
    decision: str = Field(max_length=200)
    basis: str = Field(max_length=400)


class TasteEditingStrategy(BaseModel):
    """A validated, taste-derived editing strategy.

    This is the contract between the Taste Intelligence agent and Auto Reel. It
    is intentionally a small set of global knobs that map onto EditingPlan; it
    does NOT contain per-clip IDs (those are created from the user's uploaded
    media at build time).
    """
    style_name: str = Field(default='Personalized Cinematic', max_length=80)
    aspect_ratio: Literal[ASPECT_RATIOS] = '9:16'
    pacing: Literal[PACINGS] = 'balanced'
    color_mood: Literal[STYLES] = 'cinematic'
    color_strength: float = Field(default=0.6, ge=0.0, le=1.0)
    motion: Literal[MOTIONS] = 'slow_zoom'
    clip_motion: Literal[CLIP_MOTIONS] = 'zoom_in'
    transition_preferences: List[Literal[TRANSITIONS]] = Field(
        default_factory=lambda: ['crossfade'], max_length=5)
    beat_sync: bool = True
    music_direction: str = Field(default='orchestral', max_length=60)
    storytelling: str = Field(default='atmospheric', max_length=60)
    reasoning: List[StrategyReason] = Field(default_factory=list, max_length=12)

    def primary_transition(self) -> str:
        """The first supported transition, normalized for ClipConfig.transition."""
        mapping = {'fade': 'fade', 'crossfade': 'crossfade', 'dip_black': 'dip_black',
                   'dip_white': 'dip_white', 'none': 'none'}
        for pref in self.transition_preferences:
            if pref in mapping:
                return mapping[pref]
        return 'crossfade'


class TasteStrategyResponse(BaseModel):
    """API response wrapper carrying the strategy and whether Qloo/LLM were used."""
    strategy: TasteEditingStrategy
    used_qloo: bool
    used_llm: bool
    profile_source: str
    notes: List[str] = Field(default_factory=list)
