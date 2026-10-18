import os
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any

from app.core.config import UPLOAD_DIR
from app.schemas.editing_plan import (
    EditingPlan,
    ClipConfig,
    SubtitleSegment,
    SubtitleStyle,
    TitleConfig,
    TransitionConfig,
    VisualInsert
)
from app.services.speech_transcription import (
    extract_audio_from_media,
    transcribe_audio_file,
    apply_word_emphasis
)
from app.services.visual_inserts import suggest_contextual_inserts
from app.services.audio_analysis import analyze_audio

REEL_STYLES = {
    "fitness_energy": {
        "name": "Fitness High Energy",
        "aspect_ratio": "9:16",
        "fit_mode": "fill",
        "style": "vibrant",
        "subtitle_preset": "fitness_energy",
        "caption_mode": "word_by_word",
        "pacing": "fast",
        "title_gradient": ["#F59E0B", "#EF4444"],
    },
    "minimalist": {
        "name": "Minimalist Clean",
        "aspect_ratio": "9:16",
        "fit_mode": "fit",
        "style": "minimal",
        "subtitle_preset": "minimalist",
        "caption_mode": "phrase",
        "pacing": "balanced",
        "title_gradient": ["#FFFFFF", "#E5E7EB"],
    },
    "cinematic": {
        "name": "Cinematic Story",
        "aspect_ratio": "9:16",
        "fit_mode": "fill",
        "style": "cinematic",
        "subtitle_preset": "bold_pop",
        "caption_mode": "phrase",
        "pacing": "slow",
        "title_gradient": ["#F3F4F6", "#9CA3AF"],
    }
}

def generate_auto_edit_reel(
    media_filename: str,
    style_key: str = "fitness_energy",
    available_assets: Optional[List[Dict[str, Any]]] = None,
    whisper_model: str = "tiny",
    aspect_ratio: str = "9:16",
    include_captions: bool = True,
) -> EditingPlan:
    """Generate an editable plan from validated uploads, with explicit partial-result warnings."""
    from app.services.media import uploaded_path, probe_media, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, AUDIO_EXTENSIONS
    from app.services.timeline_builder import build_timeline
    media_path = uploaded_path(media_filename)
    if style_key not in REEL_STYLES:
        raise ValueError(f"Unknown reel style: {style_key}")
    if aspect_ratio not in ("9:16", "16:9", "1:1"):
        raise ValueError("Unsupported aspect ratio.")
    is_video = media_path.suffix.lower() in VIDEO_EXTENSIONS
    is_image = media_path.suffix.lower() in IMAGE_EXTENSIONS
    if not is_video and not is_image and media_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError("Unsupported source media.")
    assets = []
    for asset in available_assets or []:
        path = uploaded_path(asset.get("filename") or asset.get("url") or asset.get("id") or "")
        if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            raise ValueError(f"Visual asset is not an image or video: {path.name}")
        if path.name != media_path.name or not is_video:
            assets.append({**asset, "filename": path.name, "url": f"/api/uploads/{path.name}"})
    if is_image and not any(a["filename"] == media_path.name for a in assets):
        assets.insert(0, {"filename": media_path.name, "url": f"/api/uploads/{media_path.name}"})
    if not is_video and not assets:
        raise ValueError("Upload at least one photo or video alongside the soundtrack.")

    warnings = []
    info = probe_media(media_path) if not is_image else {}
    if not is_image and info["duration"] <= 0:
        raise ValueError(f"Cannot read media duration: {media_path.name}")
    duration = min(60.0, info["duration"]) if is_video else min(60.0, max(1.0, len(assets) * 2.5))
    if not is_image and not is_video:
        duration = min(duration, max(1.0, info["duration"]))
    subtitles = []
    audio_info = None
    if info.get("has_audio"):
        wav_path = UPLOAD_DIR / f"auto_edit_{uuid.uuid4().hex}.wav"
        try:
            extract_audio_from_media(str(media_path), str(wav_path))
            try:
                audio_info = analyze_audio(str(wav_path))
            except Exception as exc:
                warnings.append(f"Beat analysis unavailable: {exc}")
            if include_captions:
                try:
                    subtitles = transcribe_audio_file(str(wav_path), model_size=whisper_model or "tiny")
                except Exception as exc:
                    warnings.append(f"Captions unavailable: {exc}")
        finally:
            wav_path.unlink(missing_ok=True)
    elif include_captions and is_video:
        warnings.append("This video has no audio stream; captions were not generated.")

    config = REEL_STYLES[style_key]
    sub_style = SubtitleStyle(preset=config["subtitle_preset"], caption_mode=config["caption_mode"])
    clipped_subtitles = []
    for seg in subtitles:
        if seg.start_time >= duration:
            continue
        seg.end_time = min(seg.end_time, duration)
        seg.words = [word for word in seg.words if word.start < seg.end_time]
        for word in seg.words:
            word.end = min(word.end, seg.end_time)
        seg.style = sub_style
        seg.words = apply_word_emphasis(seg.words, sub_style)
        clipped_subtitles.append(seg)
    plan = EditingPlan(
        duration_seconds=max(1.0, duration), aspect_ratio=aspect_ratio, fit_mode=config["fit_mode"],
        style=config["style"], cut_pacing=config["pacing"], beat_sync=bool(audio_info and audio_info.beat_times),
        title=TitleConfig(enabled=False, text=""), subtitles=clipped_subtitles,
        audio_filename=media_path.name if info.get("has_audio") else None, warnings=warnings,
    )
    if is_video:
        plan.clips = [ClipConfig(id="clip-main-1", image_url=f"/api/uploads/{media_path.name}",
                                start_time=0, duration=plan.duration_seconds, media_type="video",
                                motion="static", label=media_path.name)]
        if assets and clipped_subtitles:
            plan.visual_inserts = suggest_contextual_inserts(clipped_subtitles, assets,
                default_mode="split" if style_key == "minimalist" else "pip")
        elif assets:
            warnings.append("Additional visual assets remain in the library; no speech keywords matched them.")
    else:
        plan.clips = build_timeline([a["url"] for a in assets], plan, audio_info)
    for first, second in zip(plan.clips, plan.clips[1:]):
        plan.transitions.append(TransitionConfig(
            id=f"trans-{first.id}-{second.id}", from_clip_id=first.id, to_clip_id=second.id,
            type=first.transition, duration=min(0.5, first.duration - 0.1, second.duration - 0.1),
            enabled=first.transition not in ("none", "cut"),
        ))
    plan.warnings = warnings
    return plan

