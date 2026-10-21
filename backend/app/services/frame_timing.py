"""The export frame grid; source and editable timeline times remain in seconds."""
import math

OUTPUT_FPS = 30


def frame_at(seconds: float, fps: int = OUTPUT_FPS) -> int:
    # Match Math.round in preview, including exact half-frame boundaries.
    return math.floor(seconds * fps + 0.5 + 1e-9)


def clip_frame_counts(clips, fps: int = OUTPUT_FPS):
    counts = []
    elapsed = 0.0
    previous = 0
    for clip in clips:
        elapsed += clip.duration
        boundary = frame_at(elapsed, fps)
        if boundary <= previous:
            raise ValueError(f"Clip {clip.id} is too short to occupy a frame at {fps} fps.")
        counts.append(boundary - previous)
        previous = boundary
    return counts
