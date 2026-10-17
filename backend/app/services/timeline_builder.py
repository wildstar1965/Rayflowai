from typing import List, Optional
import math
from app.schemas.editing_plan import ClipConfig, EditingPlan, AudioAnalysisResult

MOTION_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]

def build_timeline(
    image_urls: List[str],
    plan: EditingPlan,
    audio_analysis: Optional[AudioAnalysisResult] = None
) -> List[ClipConfig]:
    """
    Constructs a cinematic timeline by synchronizing image durations to music beats and pacing.
    """
    if not image_urls:
        return []

    target_duration = plan.duration_seconds
    pacing = plan.cut_pacing
    num_images = len(image_urls)

    # 1. Determine cut timestamps based on audio beats if available and beat_sync is enabled
    cut_points: List[float] = [0.0]

    if audio_analysis and plan.beat_sync and audio_analysis.beat_times:
        beats = [b for b in audio_analysis.beat_times if 0.4 <= b <= target_duration - 0.4]

        # Select interval depending on pacing
        if pacing == "slow":
            # Image changes every ~4.0s - 5.0s
            step = max(3, int(round(len(beats) / max(1, target_duration / 4.0))))
            selected_beats = beats[::step]
        elif pacing == "fast":
            # Image changes every ~1.0s - 1.8s
            step = max(1, int(round(len(beats) / max(1, target_duration / 1.5))))
            selected_beats = beats[::step]
        elif pacing == "beat_driven":
            # Align with strong beats
            candidates = [b for b in audio_analysis.strong_beats if 0.5 <= b <= target_duration - 0.5]
            selected_beats = candidates if candidates else beats[::2]
        else: # "balanced"
            step = max(2, int(round(len(beats) / max(1, target_duration / 2.5))))
            selected_beats = beats[::step]

        # Filter points that are too close together (< 0.8s)
        last_t = 0.0
        for b in selected_beats:
            if b - last_t >= 0.8:
                cut_points.append(round(b, 2))
                last_t = b

    # Ensure ending boundary
    if cut_points[-1] < target_duration - 0.5:
        cut_points.append(target_duration)
    else:
        cut_points[-1] = target_duration

    # Ensure at least as many intervals as uploaded images, snapping cuts to beats
    if num_images > 1 and len(cut_points) - 1 < num_images:
        target_cuts = [i * (target_duration / num_images) for i in range(1, num_images)]
        beats = audio_analysis.beat_times if (audio_analysis and audio_analysis.beat_times) else []
        cut_points = [0.0]
        last_t = 0.0
        for tc in target_cuts:
            candidates = [b for b in beats if b - last_t >= 0.5 and target_duration - b >= 0.4]
            if candidates:
                best_b = min(candidates, key=lambda b: abs(b - tc))
                cut_points.append(round(best_b, 2))
                last_t = best_b
            else:
                cut_points.append(round(tc, 2))
                last_t = tc
        cut_points.append(target_duration)

    # 2. Build clips
    clips: List[ClipConfig] = []
    num_intervals = len(cut_points) - 1

    for i in range(num_intervals):
        start = cut_points[i]
        dur = round(cut_points[i + 1] - start, 2)
        if dur <= 0:
            continue

        # Cycle images if there are more intervals than uploaded images
        img_url = image_urls[i % num_images]
        motion = MOTION_PRESETS[i % len(MOTION_PRESETS)]

        # Transitions: fade by default, crossfade for balanced/cinematic
        transition = "crossfade" if dur >= 1.5 else "cut"

        clips.append(ClipConfig(
            id=f"clip-{i+1}",
            image_url=img_url,
            start_time=round(start, 2),
            duration=dur,
            motion=motion,
            transition=transition
        ))

    return clips
