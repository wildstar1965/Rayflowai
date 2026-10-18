from typing import List, Optional
from pathlib import Path
from app.schemas.editing_plan import ClipConfig, EditingPlan, AudioAnalysisResult
from app.services.media import VIDEO_EXTENSIONS

MOTION_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]


def build_timeline(
    image_urls: List[str],
    plan: EditingPlan,
    audio_analysis: Optional[AudioAnalysisResult] = None
) -> List[ClipConfig]:
    """Build ordered clips, retaining every asset and respecting minimum duration."""
    if not image_urls:
        return []
    minimum = 0.5
    target = max(plan.duration_seconds, len(image_urls) * minimum)
    if target > 120:
        raise ValueError("Too many assets for a 120-second reel; use at most 240.")
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
