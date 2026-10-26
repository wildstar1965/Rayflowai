"""Bounded silence removal using existing audio analysis, never model-guessed cuts."""
import copy
import math
import tempfile
import uuid


def duplicate_attachments(before, after, original, pieces):
    """Give each split its source-relative overlays before the existing retimer runs."""
    for piece in pieces:
        if piece.id == original.id:
            continue
        previous = copy.deepcopy(original)
        previous.id = piece.id
        before.clips.append(previous)
        for name in ('subtitles', 'transcript', 'visual_inserts', 'cinematic_texts', 'sound_cues'):
            for item in list(getattr(after, name)):
                if item.source_clip_id == original.id:
                    duplicate = copy.deepcopy(item)
                    duplicate.id = item.id + '-' + piece.id
                    duplicate.source_clip_id = piece.id
                    getattr(after, name).append(duplicate)


def remove_silence(plan, clip_id):
    from app.services.ai_editing import _clip, _reconcile, AIEditingError
    from app.services.media import uploaded_path
    from app.services.speech_transcription import extract_audio_from_media
    from app.services.speech_edit import quiet_windows
    from app.core.config import CACHE_DIR
    clip = _clip(plan, clip_id)
    if clip.media_type != 'video':
        raise AIEditingError('Select a video clip with recorded audio to remove silence.')
    if (clip.source_duration or clip.duration) > 1800:
        raise AIEditingError('Silence analysis supports sources up to 30 minutes. Trim the source first.')
    try:
        source = uploaded_path(clip.image_url)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE_DIR) as directory:
            wav = directory + '/analysis.wav'
            extract_audio_from_media(str(source), wav)
            quiet = quiet_windows(wav)
    except (ValueError, OSError, RuntimeError):
        raise AIEditingError('Could not analyze this clip. Check that its source media and audio are available.') from None
    runs = []
    for start, end in quiet:
        if runs and start <= runs[-1][1] + .001:
            runs[-1][1] = end
        else:
            runs.append([start, end])
    begin, finish = clip.source_start, clip.source_start + clip.duration
    cuts = []
    for start, end in runs:
        start, end = max(begin, start), min(finish, end)
        if end - start >= .7:
            # Retain room around both speech boundaries and round inward to frames.
            first, last = math.ceil((start + .15) * 30) / 30, math.floor((end - .15) * 30) / 30
            if last > first:
                cuts.append((first, last))
        if len(cuts) >= 24:
            break
    if not cuts:
        return plan, 0
    spans, cursor = [], begin
    for start, end in cuts:
        if start - cursor >= 1 / 30:
            spans.append((cursor, start))
        cursor = end
    if finish - cursor >= 1 / 30:
        spans.append((cursor, finish))
    if not spans:
        return plan, 0
    before = copy.deepcopy(plan)
    pieces = []
    for i, (start, end) in enumerate(spans):
        piece = copy.deepcopy(clip)
        piece.id = clip.id if i == 0 else clip.id + '-' + uuid.uuid4().hex[:8]
        piece.source_start, piece.duration = start, end - start
        pieces.append(piece)
    index = plan.clips.index(clip)
    plan.clips[index:index + 1] = pieces
    duplicate_attachments(before, plan, clip, pieces)
    return _reconcile(before, plan), clip.duration - sum(c.duration for c in pieces)
