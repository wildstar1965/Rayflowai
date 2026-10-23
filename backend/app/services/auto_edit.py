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
)
from app.services.speech_transcription import source_fingerprint
from app.services.speech_models import default_model
from app.services.processing import ProcessingCancelled
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
        "subtitle_preset": "cinematic",
        "caption_mode": "phrase",
        "pacing": "slow",
        "title_gradient": ["#F3F4F6", "#9CA3AF"],
    }
}

def generate_auto_edit_reel(
    media_filename: str,
    style_key: str = "cinematic",
    available_assets: Optional[List[Dict[str, Any]]] = None,
    whisper_model: Optional[str] = None,
    aspect_ratio: str = "9:16",
    include_captions: bool = True,
    current_plan: Optional[EditingPlan] = None,
    auto_broll: bool = True,
    list_sounds: bool = True,
    progress=None,
    tighten_speech: bool = False,
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

    report = progress or (lambda stage: None)
    report('Inspecting source')
    warnings = []
    info = probe_media(media_path) if not is_image else {}
    if not is_image and info["duration"] <= 0:
        raise ValueError(f"Cannot read media duration: {media_path.name}")
    duration = info["duration"] if is_video else min(120.0, max(1.0, len(assets) * 2.5))
    if not is_image and not is_video:
        duration = min(duration, max(1.0, info["duration"]))
    subtitles = []
    transcript_refreshed = False
    audio_info = None
    quiet = []
    fingerprint = source_fingerprint(media_path)
    reuse_plan = current_plan and (current_plan.source_filename == media_path.name or (
        is_video and not tighten_speech and any(Path(c.image_url).name == media_path.name for c in current_plan.clips)
    ))
    requested_model = whisper_model or default_model()
    reuse = (reuse_plan and current_plan.source_fingerprint == fingerprint and bool(current_plan.transcript)
             and current_plan.transcript_model == requested_model)
    if reuse_plan:
        report('Reusing the editable transcript and timeline')
        plan = current_plan.model_copy(deep=True)
        plan.source_filename = media_path.name
        plan.warnings = []
        plan.auto_broll = auto_broll
        plan.list_sounds = list_sounds
    if info.get("has_audio") and not reuse:
        wav_path = UPLOAD_DIR / f"auto_edit_{uuid.uuid4().hex}.wav"
        try:
            extract_audio_from_media(str(media_path), str(wav_path), cancel=getattr(report, 'cancel', None))
            if is_video and tighten_speech and not reuse_plan:
                from app.services.speech_edit import quiet_windows
                quiet = quiet_windows(wav_path)
            # Talking-head timing follows speech, not musical beats. Beat-grid
            # analysis is only consumed by the photo-montage timeline builder.
            if not is_video:
                try:
                    report('Analyzing soundtrack beats')
                    audio_info = analyze_audio(str(wav_path))
                except Exception:
                    warnings.append('Beat analysis unavailable; using evenly spaced photo cuts.')
            if include_captions or auto_broll or list_sounds:
                try:
                    report('Transcribing speech locally')
                    subtitles = transcribe_audio_file(str(wav_path), model_size=requested_model,
                        cancel=getattr(report, 'cancel', None),
                        report=lambda progress, stage, language: report(f'{stage} · {progress:.0f}%'))
                    transcript_refreshed = bool(subtitles)
                    if not subtitles and reuse_plan:
                        warnings.append('No speech was detected; existing captions and transcript were retained.')
                except ProcessingCancelled:
                    raise
                except Exception as exc:
                    warnings.append(f"Captions unavailable: {exc}")
        finally:
            wav_path.unlink(missing_ok=True)
    elif include_captions and is_video and not info.get('has_audio'):
        warnings.append("This video has no audio stream; captions were not generated.")

    if reuse_plan:
        if not reuse and transcript_refreshed:
            from app.services.caption_frames import attach_transcript
            plan.transcript = attach_transcript(subtitles, plan, media_path.name)
            if include_captions:
                manual = [s for s in plan.subtitles if s.origin == 'manual']
                plan.subtitles = manual + [s for s in plan.transcript if not any(
                    s.start_time < m.end_time and s.end_time > m.start_time for m in manual)]
            plan.cinematic_texts = [t for t in plan.cinematic_texts if t.origin == 'manual']
        if reuse or transcript_refreshed:
            plan.source_fingerprint = fingerprint
            plan.transcript_model = requested_model if plan.transcript else None
        plan.warnings.extend(warnings)
        return _enhance_plan(plan, report)
    config = REEL_STYLES[style_key]
    sub_style = SubtitleStyle(preset=config['subtitle_preset'], caption_mode='phrase')
    clipped_subtitles = []
    for seg in subtitles:
        if seg.start_time >= duration:
            continue
        seg.end_time = min(seg.end_time, duration)
        seg.words = [word for word in seg.words if word.start < seg.end_time]
        for word in seg.words:
            word.end = min(word.end, seg.end_time)
        seg.style = sub_style
        seg.origin = 'auto'
        seg.source_clip_id = 'clip-main-1' if is_video else None
        seg.source_filename = media_path.name
        clipped_subtitles.append(seg)
    from app.services.caption_engine import readable_segments
    clipped_subtitles = readable_segments(clipped_subtitles)
    plan = EditingPlan(
        duration_seconds=duration if is_video else max(1.0, duration), aspect_ratio=aspect_ratio, fit_mode=config["fit_mode"],
        style=config["style"], cut_pacing=config["pacing"], beat_sync=bool(audio_info and audio_info.beat_times),
        title=TitleConfig(enabled=False, text=""), subtitles=clipped_subtitles if include_captions else [],
        transcript=clipped_subtitles,
        audio_filename=media_path.name if info.get("has_audio") and not is_video else None, warnings=warnings,
        source_filename=media_path.name, auto_broll=auto_broll, list_sounds=list_sounds,
        source_fingerprint=fingerprint,
        transcript_model=requested_model if clipped_subtitles else None,
        color_strength=.3 if style_key == 'cinematic' else 1,
    )
    if is_video:
        plan.clips = [ClipConfig(id="clip-main-1", image_url=f"/api/uploads/{media_path.name}",
                                start_time=0, duration=plan.duration_seconds, source_duration=info['duration'], media_type="video",
                                motion="static", label=media_path.name)]
        if tighten_speech and clipped_subtitles:
            from app.services.speech_edit import speech_clips
            from app.services.caption_frames import attach_transcript
            plan.clips = speech_clips(media_path.name, duration, clipped_subtitles, quiet)
            plan.duration_seconds = sum(c.duration for c in plan.clips)
            plan.transcript = attach_transcript(clipped_subtitles, plan, media_path.name)
            plan.subtitles = plan.transcript if include_captions else []
        # Preserve the whole portrait/landscape source when filling would discard over 30%.
        source_ratio = info.get('width',1)/max(1,info.get('height',1))
        output_ratio = {'9:16':9/16,'1:1':1,'16:9':16/9}[aspect_ratio]
        if min(source_ratio/output_ratio,output_ratio/source_ratio)<.7:
            plan.fit_mode = 'fit'
        if assets and clipped_subtitles:
            plan.visual_inserts = suggest_contextual_inserts(plan.transcript, assets,
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
    return _enhance_plan(plan, report)

def _enhance_plan(plan, report):
    from app.services.broll import regenerate_broll
    from app.services.list_sounds import generate_list_cues
    from app.services.cinematic import suggest_cinematic_texts
    report('Detecting spoken lists')
    if plan.list_sounds:
        fresh = generate_list_cues(plan.subtitles or plan.transcript, plan.clips[0].id if len(plan.clips) == 1 else None)
        for cue in fresh:
            clip = next((c for c in plan.clips if c.start_time<=cue.start_time<c.start_time+c.duration), None)
            cue.source_clip_id = clip.id if clip else None
            if plan.style == 'cinematic':
                cue.volume = .22
        existing = {cue.id: cue for cue in plan.sound_cues}
        plan.sound_cues += [cue for cue in fresh if cue.id not in existing
                           and not any(abs(old.start_time - cue.start_time) < .18 for old in existing.values())]
    if plan.auto_broll and (plan.subtitles or plan.transcript):
        report('Finding relevant Pixabay B-roll')
        plan = regenerate_broll(plan)
    if not plan.cinematic_texts and plan.style == 'cinematic':
        report('Composing cinematic typography')
        plan.cinematic_texts = suggest_cinematic_texts(plan)
        from app.services.cinematic import choose_title_palette
        for title in plan.cinematic_texts:
            clip = next((c for c in plan.clips if c.id==title.source_clip_id),None)
            if clip:
                choose_title_palette(title,clip,plan.aspect_ratio,plan.fit_mode)
        from app.services.segmentation import availability, prepare_masks, mask_duration
        if plan.cinematic_texts and availability()['available']:
            title = plan.cinematic_texts[0]
            clip = next((c for c in plan.clips if c.id == title.source_clip_id), None)
            if clip and clip.media_type == 'video':
                report('Preparing the opening subject mask locally')
                try:
                    prepare_masks(clip, plan.aspect_ratio, plan.fit_mode, mask_duration(plan, clip), progress=report)
                    from PIL import Image
                    from app.services.segmentation import existing_masks
                    from app.services.cinematic import place_title_with_mattes
                    directory = existing_masks(clip, plan.aspect_ratio, plan.fit_mode, mask_duration(plan, clip))
                    samples = []
                    for fraction in (.1, .5, .9):
                        frame = max(0, int((title.start_time-clip.start_time+title.duration*fraction)*30))
                        with Image.open(directory / f'{frame:05d}.png') as matte:
                            samples.append(matte.convert('L'))
                    place_title_with_mattes(title, samples)
                except ProcessingCancelled:
                    raise
                except Exception:
                    plan.warnings.append('Subject masking could not be prepared. The opening uses regular typography; other edits are retained.')
        elif plan.cinematic_texts and any(c.media_type == 'video' for c in plan.clips):
            plan.warnings.append(availability()['message'])
    report('Draft ready')
    return plan

