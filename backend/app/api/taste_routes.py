"""Taste AI routes: profile management, analysis, and taste-driven editing.

All routes are workspace-scoped using the same session/ownership model as the
rest of the editor. The Qloo API key is backend-only and never returned. No user
media is ever sent to Qloo — only declared cultural preferences (names/genres).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.editing_plan import EditingPlan
from app.schemas.taste import TasteEditingStrategy, TasteStrategyResponse
from app.services.provider_settings import setting
from app.services.qloo.client import QlooError, qloo_configured
from app.services.qloo.profile_builder import TasteProfile, build_profile
from app.services.taste_intelligence import generate_strategy
from app.services.taste_reel import apply_strategy_to_plan

logger = logging.getLogger('rayflow.taste')

router = APIRouter(prefix='/api/taste', tags=['taste'])

TASTE_COLLECTION = 'taste_profiles'
MAX_PREFERENCES = 40

# Small per-workspace rate guard for Qloo-backed analysis calls.
_analyze_calls: dict[str, deque[float]] = defaultdict(deque)


class PreferenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=200)
    category: str = Field(default='movie', max_length=40)


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preferences: List[PreferenceInput] = Field(default_factory=list, max_length=MAX_PREFERENCES)
    use_qloo: bool = True


class EditPlanRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allow_llm: bool = True


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_plan: EditingPlan
    strategy: Optional[TasteEditingStrategy] = None
    allow_llm: bool = True


class TasteReelRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    media_filename: str
    available_assets: Optional[list] = None
    whisper_model: Optional[str] = None
    include_captions: bool = False
    current_plan: Optional[EditingPlan] = None
    auto_broll: bool = False
    list_sounds: bool = False
    tighten_speech: bool = False
    allow_llm: bool = True


def _owner() -> str:
    from app.editor.context import workspace_id
    identity = workspace_id.get()
    if not identity:
        raise HTTPException(401, 'A workspace session is required for taste profiles.')
    return identity


def _load_profile(identity: str) -> Optional[TasteProfile]:
    from app.editor.store import store
    record = store.get(TASTE_COLLECTION, identity, identity)
    if not record:
        return None
    payload = {k: v for k, v in record.items() if k not in ('id', 'revision')}
    try:
        return TasteProfile.model_validate(payload)
    except ValueError:
        logger.warning('Stored taste profile for %s is invalid; ignoring.', identity)
        return None


def _save_profile(identity: str, profile: TasteProfile) -> None:
    from app.editor.store import store
    store.put(TASTE_COLLECTION, identity, identity, profile.model_dump(mode='json'))


def _rate_limit(identity: str) -> None:
    now = time.monotonic()
    recent = _analyze_calls[identity]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= 12:
        raise HTTPException(429, 'Taste analysis limit reached. Please wait a moment.')
    recent.append(now)


def _build(preferences, use_qloo: bool) -> TasteProfile:
    effective_qloo = bool(use_qloo and qloo_configured())
    try:
        profile = build_profile(
            [p.model_dump() for p in preferences], use_qloo=effective_qloo)
    except QlooError as exc:
        # Qloo failed mid-flight: degrade to a declared-only profile with a note.
        profile = build_profile([p.model_dump() for p in preferences], use_qloo=False)
        profile.notes.append(f'Qloo analysis failed: {exc}')
    if use_qloo and not qloo_configured():
        profile.notes.append('Qloo is not configured on the backend; profile reflects declared preferences only.')
    return profile


@router.get('/profile')
def get_profile():
    identity = _owner()
    profile = _load_profile(identity)
    if not profile:
        return {'exists': False, 'profile': None, 'qloo_configured': qloo_configured()}
    return {'exists': True, 'profile': profile.model_dump(mode='json'),
            'summary': profile.summary(), 'qloo_configured': qloo_configured()}


@router.post('/profile')
def create_profile(request: ProfileRequest, http_request: Request):
    from app.editor.security import require_origin
    require_origin(http_request)
    identity = _owner()
    if not request.preferences:
        raise HTTPException(422, 'Add at least one preference to build a taste profile.')
    _rate_limit(identity)
    profile = _build(request.preferences, request.use_qloo)
    _save_profile(identity, profile)
    return {'exists': True, 'profile': profile.model_dump(mode='json'),
            'summary': profile.summary(), 'qloo_configured': qloo_configured()}


@router.put('/profile')
def update_profile(request: ProfileRequest, http_request: Request):
    from app.editor.security import require_origin
    require_origin(http_request)
    identity = _owner()
    if not request.preferences:
        raise HTTPException(422, 'Add at least one preference to update the taste profile.')
    _rate_limit(identity)
    existing = _load_profile(identity)
    profile = _build(request.preferences, request.use_qloo)
    if existing:
        profile.created_at = existing.created_at
    profile.updated_at = time.time()
    _save_profile(identity, profile)
    return {'exists': True, 'profile': profile.model_dump(mode='json'),
            'summary': profile.summary(), 'qloo_configured': qloo_configured()}


@router.post('/analyze')
def analyze(request: ProfileRequest, http_request: Request):
    """Resolve + analyze preferences WITHOUT persisting (preview before saving)."""
    from app.editor.security import require_origin
    require_origin(http_request)
    identity = _owner()
    if not request.preferences:
        raise HTTPException(422, 'Add at least one preference to analyze.')
    _rate_limit(identity)
    profile = _build(request.preferences, request.use_qloo)
    return {'summary': profile.summary(),
            'resolved_entities': [e.model_dump() for e in profile.resolved_entities],
            'resolved_tags': [t.model_dump() for t in profile.resolved_tags],
            'cultural_associations': [a.model_dump() for a in profile.cultural_associations],
            'unresolved': [u.model_dump() for u in profile.unresolved],
            'qloo_configured': qloo_configured()}


@router.post('/edit-plan', response_model=TasteStrategyResponse)
def edit_plan(request: EditPlanRequest, http_request: Request):
    """Generate a validated taste editing strategy from the saved profile."""
    from app.editor.security import require_origin
    require_origin(http_request)
    identity = _owner()
    profile = _load_profile(identity)
    if not profile:
        raise HTTPException(404, 'Create a taste profile first in "Discover Your Taste".')
    allow_llm = request.allow_llm and setting('AI_PROVIDER', 'auto') != 'local'
    return generate_strategy(profile.summary(), allow_llm=allow_llm)


@router.post('/apply')
def apply(request: ApplyRequest, http_request: Request):
    """Return a taste-adjusted copy of the current plan for review (not auto-applied).

    The frontend presents this through the existing review/approval UI; nothing
    is persisted to the active project until the user approves it.
    """
    from app.editor.security import require_origin
    require_origin(http_request)
    identity = _owner()
    strategy = request.strategy
    strategy_response = None
    if strategy is None:
        profile = _load_profile(identity)
        if not profile:
            raise HTTPException(404, 'Create a taste profile first in "Discover Your Taste".')
        allow_llm = request.allow_llm and setting('AI_PROVIDER', 'auto') != 'local'
        strategy_response = generate_strategy(profile.summary(), allow_llm=allow_llm)
        strategy = strategy_response.strategy
    proposed = apply_strategy_to_plan(request.current_plan.model_copy(deep=True), strategy)
    proposed = EditingPlan.model_validate(proposed.model_dump())
    return {
        'proposed_plan': proposed.model_dump(mode='json'),
        'strategy': strategy.model_dump(mode='json'),
        'reasoning': [r.model_dump() for r in strategy.reasoning],
        'used_qloo': strategy_response.used_qloo if strategy_response else None,
        'used_llm': strategy_response.used_llm if strategy_response else None,
    }


@router.post('/reel/jobs')
def taste_reel_job(request: TasteReelRequest, http_request: Request):
    """Start an async 'Create a Reel Based on My Taste' job.

    Builds a strategy from the saved taste profile, then generates a normal,
    editable reel via the existing Auto Reel engine with the strategy overlaid.
    Returns a creative job id the frontend polls like any other Auto Reel job.
    """
    from app.editor.security import require_origin
    from app.services.creative_jobs import start_job
    from app.services.media import uploaded_path
    from app.services.taste_reel import generate_taste_reel

    require_origin(http_request)
    identity = _owner()
    profile = _load_profile(identity)
    if not profile:
        raise HTTPException(404, 'Create a taste profile first in "Discover Your Taste".')

    allow_llm = request.allow_llm and setting('AI_PROVIDER', 'auto') != 'local'
    strategy_response = generate_strategy(profile.summary(), allow_llm=allow_llm)
    strategy = strategy_response.strategy

    try:
        uploaded_path(request.media_filename)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from None

    def run(report):
        plan = generate_taste_reel(
            media_filename=request.media_filename,
            strategy=strategy,
            available_assets=request.available_assets,
            whisper_model=request.whisper_model,
            include_captions=request.include_captions,
            current_plan=request.current_plan,
            auto_broll=request.auto_broll,
            list_sounds=request.list_sounds,
            progress=report,
            tighten_speech=request.tighten_speech,
        )
        result = plan.model_dump()
        # Attach the taste strategy + reasoning so the UI can explain the edit.
        result['taste'] = {
            'strategy': strategy.model_dump(mode='json'),
            'reasoning': [r.model_dump() for r in strategy.reasoning],
            'used_qloo': strategy_response.used_qloo,
            'used_llm': strategy_response.used_llm,
            'profile_source': strategy_response.profile_source,
        }
        return result

    try:
        job_id = start_job(run)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from None
    return {'job_id': job_id, 'strategy': strategy.model_dump(mode='json'),
            'used_qloo': strategy_response.used_qloo, 'used_llm': strategy_response.used_llm}
