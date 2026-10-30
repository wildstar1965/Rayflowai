"""Apply a validated taste strategy to RayFlow's editing engine.

This does NOT reimplement the timeline or renderer. It builds on the existing
``generate_auto_edit_reel`` by selecting the closest base template and then
overlaying the taste-derived global knobs (style, pacing, motion, color,
transitions, beat sync) onto the resulting editable plan. The output is a normal
``EditingPlan`` the user can freely modify and render with the existing FFmpeg
pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.editing_plan import EditingPlan, TransitionConfig
from app.schemas.taste import TasteEditingStrategy
from app.services.auto_edit import generate_auto_edit_reel

# Map a taste color_mood/pacing to the nearest existing Auto Reel base template
# so caption presets and defaults stay consistent with the rest of the product.
_TEMPLATE_FOR_MOOD = {
    'vibrant': 'fitness_energy',
    'minimal': 'minimalist',
    'cinematic': 'cinematic',
    'vintage': 'cinematic',
    'noir': 'cinematic',
}


def base_template_for(strategy: TasteEditingStrategy) -> str:
    if strategy.pacing == 'fast':
        return 'fitness_energy'
    if strategy.color_mood == 'minimal':
        return 'minimalist'
    return _TEMPLATE_FOR_MOOD.get(strategy.color_mood, 'cinematic')


def apply_strategy_to_plan(plan: EditingPlan, strategy: TasteEditingStrategy) -> EditingPlan:
    """Overlay taste-derived global settings onto an existing editable plan."""
    plan.style = strategy.color_mood
    plan.color_strength = strategy.color_strength
    plan.cut_pacing = 'beat_driven' if (strategy.pacing == 'beat_driven') else strategy.pacing
    plan.motion = strategy.motion
    plan.beat_sync = strategy.beat_sync
    plan.aspect_ratio = strategy.aspect_ratio

    transition = strategy.primary_transition()
    # Apply the preferred clip motion and transition across the montage clips.
    for clip in plan.clips:
        if clip.media_type == 'image':
            clip.motion = strategy.clip_motion
        clip.transition = transition

    # Rebuild transition records to reflect the taste preference between clips.
    rebuilt: List[TransitionConfig] = []
    for first, second in zip(plan.clips, plan.clips[1:]):
        rebuilt.append(TransitionConfig(
            id=f'taste-trans-{first.id}-{second.id}',
            from_clip_id=first.id, to_clip_id=second.id,
            type=transition,
            duration=min(0.5, max(0.1, first.duration - 0.1), max(0.1, second.duration - 0.1)),
            enabled=transition not in ('none', 'cut'),
        ))
    plan.transitions = rebuilt
    return plan


def generate_taste_reel(
    media_filename: str,
    strategy: TasteEditingStrategy,
    available_assets: Optional[List[Dict[str, Any]]] = None,
    whisper_model: Optional[str] = None,
    include_captions: bool = False,
    current_plan: Optional[EditingPlan] = None,
    auto_broll: bool = False,
    list_sounds: bool = False,
    progress=None,
    tighten_speech: bool = False,
) -> EditingPlan:
    """Generate a personalized, editable reel from uploaded media + a taste strategy."""
    report = progress or (lambda stage: None)
    report('Selecting a base template from your taste')
    base = base_template_for(strategy)

    plan = generate_auto_edit_reel(
        media_filename=media_filename,
        style_key=base,
        available_assets=available_assets,
        whisper_model=whisper_model,
        aspect_ratio=strategy.aspect_ratio,
        include_captions=include_captions,
        current_plan=current_plan,
        auto_broll=auto_broll,
        list_sounds=list_sounds,
        progress=report,
        tighten_speech=tighten_speech,
    )

    report('Applying your personalized taste strategy')
    plan = apply_strategy_to_plan(plan, strategy)
    # Record provenance in warnings-free metadata via style_name on the title is
    # avoided to not override user title; the strategy is returned via the API.
    return EditingPlan.model_validate(plan.model_dump())
