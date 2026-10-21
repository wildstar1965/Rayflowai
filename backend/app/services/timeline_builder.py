from typing import List, Optional
from pathlib import Path
import uuid
from app.schemas.editing_plan import ClipConfig, EditingPlan, AudioAnalysisResult
from app.services.media import VIDEO_EXTENSIONS, probe_media, uploaded_path

MOTION_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]


def build_timeline(
    image_urls: List[str],
    plan: EditingPlan,
    audio_analysis: Optional[AudioAnalysisResult] = None
) -> List[ClipConfig]:
    """Keep existing edits; initialize videos from their complete source range."""
    if not image_urls:
        return []
    if plan.clips or any(Path(url).suffix.lower() in VIDEO_EXTENSIONS for url in image_urls):
        urls = {Path(url).name: url for url in image_urls}
        clips = [c.model_copy(deep=True) for c in plan.clips if Path(c.image_url).name in urls]
        retained = {Path(c.image_url).name for c in clips}
        for url in image_urls:
            if Path(url).name in retained:
                continue
            is_video = Path(url).suffix.lower() in VIDEO_EXTENSIONS
            duration = probe_media(uploaded_path(url))['duration'] if is_video else 2.5
            if duration <= 0:
                raise ValueError(f"Cannot read source duration: {url}")
            clips.append(ClipConfig(
                id=f"clip-{uuid.uuid4().hex[:12]}", image_url=url, start_time=0,
                duration=duration, source_start=0, source_duration=duration if is_video else None,
                media_type='video' if is_video else 'image', motion='static' if is_video else 'zoom_in',
                transition='crossfade' if duration >= 1.5 else 'cut',
            ))
            retained.add(Path(url).name)
        cursor = 0.0
        for clip in clips:
            clip.start_time = cursor
            cursor += clip.duration
        plan.duration_seconds = cursor
        return clips
    minimum = 0.5
    target = max(plan.duration_seconds, len(image_urls) * minimum)
    plan.duration_seconds = target
    pacing_seconds = {"slow": 4.0, "balanced": 2.5, "fast": 1.5, "beat_driven": 1.0}
    count = max(len(image_urls), round(target / pacing_seconds.get(plan.cut_pacing, 2.5)))
    # Without beats, give each uploaded item one complete slot.
    beats = []
    if audio_analysis and plan.beat_sync:
        beats = audio_analysis.strong_beats if plan.cut_pacing == "beat_driven" else audio_analysis.beat_times
        beats = sorted(set(b for b in beats if 0 < b < target))
    if not beats:
        count = len(image_urls)
    count = min(count, int(target / minimum))
    cuts = [0.0]
    for i in range(1, count):
        ideal = target * i / count
        lower = cuts[-1] + minimum
        upper = target - (count - i) * minimum
        candidates = [b for b in beats if lower <= b <= upper]
        point = min(candidates, key=lambda b: abs(b - ideal)) if candidates else max(lower, min(ideal, upper))
        cuts.append(round(point, 6))
    cuts.append(target)
    clips = []
    for i in range(count):
        url = image_urls[i % len(image_urls)]
        is_video = Path(url).suffix.lower() in VIDEO_EXTENSIONS
        duration = round(cuts[i + 1] - cuts[i], 6)
        motion = "static" if is_video or plan.motion == "static" else MOTION_PRESETS[i % len(MOTION_PRESETS)]
        clips.append(ClipConfig(
            id=f"clip-{i+1}", image_url=url, start_time=cuts[i], duration=duration,
            media_type="video" if is_video else "image", motion=motion,
            transition="crossfade" if duration >= 1.5 else "cut",
        ))
    return clips
