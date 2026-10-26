"""Shared caption segmentation, local raster layout and export frame track."""
import hashlib
import json
import threading
from PIL import Image
from app.core.config import CACHE_DIR
from app.schemas.editing_plan import SubtitleStyle
from app.services.caption_engine import cue_windows, active_word_windows, timed_words
from app.services.caption_layout import paint_caption
from app.services.cinematic import atomic_png, write_frame_track

_CAPTION_LOCK = threading.Lock()


def attach_transcript(segments, plan, source_filename):
    """Map source timestamps onto every trimmed/reordered occurrence of that media."""
    from pathlib import Path
    result = []
    clips = [c for c in plan.clips if Path(c.image_url).name == source_filename and c.media_type == 'video']
    for clip in clips or [None]:
        source_start = clip.source_start if clip else 0
        duration = clip.duration if clip else plan.duration_seconds
        offset = clip.start_time-source_start if clip else 0
        for segment in segments:
            start, end = max(source_start, segment.start_time), min(source_start+duration, segment.end_time)
            if end <= start:
                continue
            item = segment.model_copy(deep=True)
            item.id = f'{clip.id if clip else "audio"}-{segment.id}'
            item.source_clip_id = clip.id if clip else None
            item.source_filename = source_filename
            item.origin = 'auto'
            item.start_time, item.end_time = start+offset, end+offset
            item.words = []
            for word in segment.words:
                if word.end <= start or word.start >= end:
                    continue
                copied = word.model_copy(deep=True)
                copied.start, copied.end = max(start, word.start)+offset, min(end, word.end)+offset
                item.words.append(copied)
            if item.words and len(item.words) != len(segment.words):
                item.text = ' '.join(w.word for w in item.words)
            result.append(item)
    return sorted(result, key=lambda s: s.start_time)


def caption_units(segment, end):
    style = segment.style or SubtitleStyle()
    words = timed_words(segment)
    if not words:
        return [(segment.start_time, end, [{'word': line, 'line_before': index > 0}
                 for index, line in enumerate(segment.text.split('\n')) if line], None)]
    units = []
    for start, finish, group in cue_windows(words, style, segment.start_time, end):
        if style.highlight_active and style.caption_mode != 'word_by_word':
            if start < group[0]['start']:
                units.append((start, group[0]['start'], group, None))
            units.extend((begin, stop, group, active) for begin, stop, active
                         in active_word_windows(group, start, finish))
        else:
            units.append((start, finish, group, None))
    return units


def caption_events(segments, width, height, check=None, include_bounds=False):
    events = []
    bounds = {}
    ordered = sorted(segments, key=lambda s: s.start_time)
    for index, segment in enumerate(ordered):
        end = min(segment.end_time, ordered[index+1].start_time) if index+1 < len(ordered) else segment.end_time
        style = segment.style or SubtitleStyle()
        for start, finish, words, active in caption_units(segment, end):
            if check:
                check()
            if finish <= start or not segment.text.strip():
                continue
            # Timing doesn't change static glyphs; active word index does.
            glyphs = [{k: v for k, v in w.items() if k not in ('start', 'end')} for w in words]
            key = hashlib.sha256(json.dumps(['captions-v7-stable', glyphs, active, style.model_dump(), width, height], sort_keys=True).encode()).hexdigest()
            path = CACHE_DIR / f'caption_{key}.png'
            with _CAPTION_LOCK:
                if not path.exists():
                    atomic_png(_paint(glyphs, style, width, height, active), path)
            event = {'start_time': start, 'end_time': finish,
                     'url': f'/api/cinematic/captions/{key}.png', 'path': str(path)}
            if include_bounds:
                if key not in bounds:
                    with Image.open(path) as raster:
                        box = raster.getchannel('A').getbbox()
                    bounds[key] = [box[0]/width, box[1]/height, (box[2]-box[0])/width, (box[3]-box[1])/height] if box else None
                event.update(caption_id=segment.id, bounds=bounds[key])
            events.append(event)
    return events


def _paint(words, style, width, height, active=None):
    return paint_caption(words, style, width, height, active)


def caption_track(events, width, height, duration, destination):
    blank = CACHE_DIR / f'caption_blank_{width}_{height}.png'
    with _CAPTION_LOCK:
        if not blank.exists():
            atomic_png(Image.new('RGBA', (width, height)), blank)
    def frames():
        cursor = 0
        for frame in range(max(1, round(duration*30))):
            time = frame/30
            while cursor < len(events) and events[cursor]['end_time'] <= time:
                cursor += 1
            yield events[cursor]['path'] if cursor < len(events) and events[cursor]['start_time'] <= time < events[cursor]['end_time'] else blank
    return write_frame_track(frames(), destination)
