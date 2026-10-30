"""Taste Intelligence agent.

Bridges Qloo cultural intelligence and RayFlow's existing AI provider stack. It
feeds the user's taste profile (declared preferences + REAL Qloo-derived
associations/tags) to the configured LLM and asks for a STRUCTURED editing
strategy, which is then validated against ``TasteEditingStrategy`` before any
use. The LLM is explicitly instructed to reason only from the supplied Qloo data
and never invent cultural associations.

If no LLM provider is configured, a deterministic, rule-based mapping derives a
strategy from the Qloo tag signals so the feature still works without keys.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.schemas.taste import (
    PACINGS,
    STYLES,
    TasteEditingStrategy,
    TasteStrategyResponse,
    StrategyReason,
)
from app.services.ai_provider import generate_plan, ProviderError
from app.services.provider_settings import setting

logger = logging.getLogger('rayflow.taste')

SYSTEM_PROMPT = (
    "You are RayFlow's Taste Intelligence director. You translate a user's "
    "cultural taste profile into concrete, SUPPORTED video-editing choices. "
    "You are given: (1) preferences the user explicitly DECLARED, and (2) "
    "cultural associations and tag signals DERIVED BY QLOO from those preferences. "
    "Reason ONLY from this supplied data. Never invent movies, artists, tags, or "
    "cultural facts that are not present in the input. "
    "Return ONLY a JSON object with these exact keys: "
    "style_name (string), aspect_ratio (one of 9:16,16:9,1:1), "
    "pacing (one of slow,balanced,fast,beat_driven), "
    "color_mood (one of cinematic,vintage,noir,vibrant,minimal), "
    "color_strength (number 0..1), motion (one of slow_zoom,dynamic,static), "
    "clip_motion (one of zoom_in,zoom_out,pan_left,pan_right,static), "
    "transition_preferences (array of: none,crossfade,dip_black,dip_white,fade), "
    "beat_sync (boolean), music_direction (short string), "
    "storytelling (short string), and reasoning (array of objects with "
    "'decision' and 'basis', where 'basis' cites the specific declared preference "
    "or Qloo signal that justified the decision). "
    "Choose values that reflect the taste profile: e.g. atmospheric/orchestral, "
    "cinematic signals favor slower pacing, cinematic color, slow_zoom and "
    "crossfades; high-energy/pop signals favor fast pacing, vibrant color and "
    "dynamic motion. Keep every value within the allowed sets."
)


def generate_strategy(profile_summary: dict, allow_llm: bool = True) -> TasteStrategyResponse:
    """Produce a validated editing strategy from a taste profile summary dict.

    ``profile_summary`` is ``TasteProfile.summary()`` — it contains only names,
    types, tags and affinities, never any user media.
    """
    used_qloo = bool(
        profile_summary.get('resolved_entities')
        or profile_summary.get('cultural_associations')
        or profile_summary.get('tag_signals')
    )
    profile_source = 'qloo' if used_qloo else 'declared_only'
    provider_selected = setting('AI_PROVIDER', 'auto')
    llm_available = _llm_available(provider_selected)

    if allow_llm and llm_available:
        try:
            strategy = _llm_strategy(profile_summary)
            return TasteStrategyResponse(
                strategy=strategy, used_qloo=used_qloo, used_llm=True,
                profile_source=profile_source,
                notes=profile_summary.get('notes', []))
        except (ProviderError, ValueError, TypeError, KeyError) as exc:
            logger.info('Taste LLM strategy failed, falling back to rules: %s', exc)
            notes = list(profile_summary.get('notes', []))
            notes.append('AI interpretation was unavailable; a rule-based strategy was used.')
            strategy = _rule_based_strategy(profile_summary)
            return TasteStrategyResponse(
                strategy=strategy, used_qloo=used_qloo, used_llm=False,
                profile_source=profile_source, notes=notes)

    strategy = _rule_based_strategy(profile_summary)
    return TasteStrategyResponse(
        strategy=strategy, used_qloo=used_qloo, used_llm=False,
        profile_source=profile_source, notes=profile_summary.get('notes', []))


def _llm_available(provider_selected: str) -> bool:
    if provider_selected == 'local':
        return False
    if provider_selected == 'ollama':
        return True
    if provider_selected not in ('auto', ''):
        return bool(setting(provider_selected.upper() + '_API_KEY'))
    # auto: any configured hosted provider key counts.
    for provider in ('gemini', 'openai', 'anthropic', 'openrouter', 'agentrouter'):
        if setting(provider.upper() + '_API_KEY'):
            return True
    return False


def _llm_strategy(profile_summary: dict) -> TasteEditingStrategy:
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': json.dumps({'taste_profile': profile_summary}, separators=(',', ':'))},
    ]
    raw = generate_plan(messages)
    if not isinstance(raw, dict):
        raise ValueError('The provider returned a non-object strategy.')
    # Validate strictly; invalid values raise and trigger the rule-based fallback.
    return TasteEditingStrategy.model_validate(raw)


# --- Deterministic fallback -------------------------------------------------

# Keyword buckets used to infer a mood from Qloo tag/association names without an
# LLM. These are heuristics over Qloo-DERIVED data, not invented associations.
_FAST_WORDS = ('energy', 'workout', 'fitness', 'edm', 'dance', 'pop', 'hip hop', 'rap', 'party', 'action')
_CINEMATIC_WORDS = ('cinematic', 'atmospheric', 'epic', 'orchestral', 'score', 'drama', 'sci-fi', 'thriller', 'nolan', 'zimmer')
_VINTAGE_WORDS = ('vintage', 'retro', 'classic', 'folk', 'jazz', 'nostalg', '80s', '70s')
_NOIR_WORDS = ('noir', 'dark', 'moody', 'crime', 'mystery', 'melancho')
_MINIMAL_WORDS = ('minimal', 'clean', 'ambient', 'acoustic', 'calm', 'indie')


def _rule_based_strategy(profile_summary: dict) -> TasteEditingStrategy:
    corpus = _corpus(profile_summary)
    scores = {
        'fast': sum(corpus.count(w) for w in _FAST_WORDS),
        'cinematic': sum(corpus.count(w) for w in _CINEMATIC_WORDS),
        'vintage': sum(corpus.count(w) for w in _VINTAGE_WORDS),
        'noir': sum(corpus.count(w) for w in _NOIR_WORDS),
        'minimal': sum(corpus.count(w) for w in _MINIMAL_WORDS),
    }
    bucket = max(scores, key=scores.get) if any(scores.values()) else 'cinematic'
    reasons: List[StrategyReason] = []

    if bucket == 'fast':
        strategy = TasteEditingStrategy(
            style_name='Personalized High Energy', pacing='fast', color_mood='vibrant',
            color_strength=1.0, motion='dynamic', clip_motion='zoom_in',
            transition_preferences=['crossfade', 'fade'], beat_sync=True,
            music_direction='driving', storytelling='punchy')
        reasons.append(StrategyReason(decision='fast pacing, vibrant color',
                                      basis='High-energy signals in the Qloo taste profile'))
    elif bucket == 'vintage':
        strategy = TasteEditingStrategy(
            style_name='Personalized Vintage', pacing='balanced', color_mood='vintage',
            color_strength=0.8, motion='slow_zoom', clip_motion='zoom_in',
            transition_preferences=['fade', 'crossfade'], beat_sync=True,
            music_direction='nostalgic', storytelling='reflective')
        reasons.append(StrategyReason(decision='vintage color grade',
                                      basis='Retro/classic signals in the Qloo taste profile'))
    elif bucket == 'noir':
        strategy = TasteEditingStrategy(
            style_name='Personalized Noir', pacing='slow', color_mood='noir',
            color_strength=0.9, motion='slow_zoom', clip_motion='static',
            transition_preferences=['dip_black', 'crossfade'], beat_sync=False,
            music_direction='moody', storytelling='suspenseful')
        reasons.append(StrategyReason(decision='noir grade, slow pacing',
                                      basis='Dark/moody signals in the Qloo taste profile'))
    elif bucket == 'minimal':
        strategy = TasteEditingStrategy(
            style_name='Personalized Minimal', pacing='balanced', color_mood='minimal',
            color_strength=0.4, motion='static', clip_motion='static',
            transition_preferences=['crossfade'], beat_sync=True,
            music_direction='ambient', storytelling='clean')
        reasons.append(StrategyReason(decision='minimal, restrained motion',
                                      basis='Minimal/ambient signals in the Qloo taste profile'))
    else:  # cinematic default
        strategy = TasteEditingStrategy(
            style_name='Personalized Cinematic', pacing='slow', color_mood='cinematic',
            color_strength=0.5, motion='slow_zoom', clip_motion='zoom_in',
            transition_preferences=['crossfade', 'dip_black'], beat_sync=True,
            music_direction='orchestral', storytelling='atmospheric')
        reasons.append(StrategyReason(decision='cinematic grade, slow pacing, crossfades',
                                      basis='Cinematic/atmospheric signals in the Qloo taste profile'))

    top_tags = [t.get('name') for t in profile_summary.get('tag_signals', [])[:5] if t.get('name')]
    if top_tags:
        reasons.append(StrategyReason(
            decision='music and mood direction',
            basis='Top Qloo tag signals: ' + ', '.join(top_tags)))
    strategy.reasoning = reasons
    return strategy


def _corpus(profile_summary: dict) -> str:
    parts: List[str] = []
    for item in profile_summary.get('declared', []):
        parts.append(str(item.get('text', '')))
    for item in profile_summary.get('resolved_entities', []):
        parts.append(str(item.get('name', '')))
    for item in profile_summary.get('cultural_associations', []):
        parts.append(str(item.get('name', '')))
    for item in profile_summary.get('tag_signals', []):
        parts.append(str(item.get('name', '')))
    return ' '.join(parts).lower()
