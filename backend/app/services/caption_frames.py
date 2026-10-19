"""Shared caption segmentation, local raster layout and export frame track."""
import hashlib
import json
import math
import re
import threading
from PIL import Image, ImageDraw
from app.core.config import CACHE_DIR
from app.schemas.editing_plan import SubtitleStyle
from app.services.cinematic import local_font, text_length, draw_tracked, atomic_png, write_frame_track

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
    words = [w.model_dump() for w in segment.words if w.end > w.start and w.word.strip()]
    # A corrected phrase with stale or partial word metadata must display the correction.
    if re.sub(r'\s+', '', ''.join(w['word'] for w in words)) != re.sub(r'\s+', '', segment.text):
        words = []
    if not words:
        return [(segment.start_time, end, [{'word': line, 'line_before': index > 0}
                 for index, line in enumerate(segment.text.split('\n')) if line], None)]
    cursor = 0
    for index, word in enumerate(words):
        at = segment.text.find(word['word'], cursor)
        gap = segment.text[cursor:at]
        word['line_before'] = '\n' in gap
        word['join_left'] = index > 0 and not gap
        cursor = at+len(word['word'])
    groups, group = [], []
    for word in words:
        length = len(' '.join(w['word'] for w in group+[word]))
        if group and (style.caption_mode == 'word_by_word' or length > style.max_chars
                      or word['end']-group[0]['start'] > style.max_duration):
            groups.append(group)
            group = []
        group.append(word)
        abbreviation = word['word'].casefold() in {'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'e.g.', 'i.e.'}
        if not abbreviation and re.search(r'[.!?][\'")]*$', word['word']):
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    units = []
    for index, group in enumerate(groups):
        start = max(segment.start_time, group[0]['start']) if index else segment.start_time
        finish = min(end, groups[index+1][0]['start']) if index+1 < len(groups) else end
        finish = min(finish, max(group[-1]['end'], start+style.max_duration))
        if finish <= start:
            continue
        if style.highlight_active and style.caption_mode != 'word_by_word':
            boundaries = sorted({start, finish, *[max(start, min(finish, w[k])) for w in group for k in ('start', 'end')]})
            for begin, stop in zip(boundaries, boundaries[1:]):
                active = next((i for i, w in enumerate(group) if w['start'] <= begin < w['end']), None)
                units.append((begin, stop, group, active))
        else:
            units.append((start, finish, group, None))
    return units


def caption_events(segments, width, height, check=None):
    events = []
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
            if style.caption_mode == 'word_by_word' and style.preset != 'cinematic':
                glyphs = [{**w, 'word':w['word'].upper() if w.get('emphasis') else w['word']} for w in glyphs]
            key = hashlib.sha256(json.dumps(['captions-v5', glyphs, active, style.model_dump(), width, height], sort_keys=True).encode()).hexdigest()
            path = CACHE_DIR / f'caption_{key}.png'
            with _CAPTION_LOCK:
                if not path.exists():
                    atomic_png(_paint(glyphs, style, width, height, active), path)
            events.append({'start_time': start, 'end_time': finish,
                           'url': f'/api/cinematic/captions/{key}.png', 'path': str(path)})
    return events


def _paint(words, style, width, height, active=None):
    size = style.font_size
    tracking = style.tracking*width/1080
    margin = max(style.stroke_width+2, math.ceil(width*.08))
    usable = width-2*margin
    while True:
        base = local_font(size, style.font_family, style.font_weight)
        space = text_length(' ', base, tracking)+tracking
        lines, current, used = [], [], 0
        for index, word in enumerate(words):
            emphasis = word.get('emphasis', False)
            multiplier = word.get('size_multiplier', 1.15 if emphasis else 1)
            font = local_font(round(size*multiplier), style.font_family, max(style.font_weight, 700) if emphasis else style.font_weight)
            # Split fallback paragraphs spatially, without fabricating word times.
            for token_index, token in enumerate(word['word'].split()):
                length = text_length(token, font, tracking)
                gap = 0 if word.get('join_left') and token_index == 0 else space
                if current and (used+gap+length > usable or (word.get('line_before') and token_index == 0)):
                    lines.append((current, used))
                    current, used = [], 0
                gap = gap if current else 0
                current.append((token, font, length, word, index, gap))
                used += length+gap
        if current:
            lines.append((current, used))
        line_height = size*max(1.35, max((w.get('size_multiplier', 1) for w in words), default=1)*1.2)
        if size <= 10 or (all(length <= usable for _, length in lines) and len(lines)*line_height < height*.75):
            break
        size -= 2
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)
    center = height*(.12 if style.position == 'top' else .5 if style.position == 'middle' else .86)
    block_height = len(lines)*line_height
    y = min(max(height*.05, center-block_height/2), height*.95-block_height)
    for line, length in lines:
        x = (width-length)/2
        for token, font, token_width, word, index, gap in line:
            x += gap
            color = style.highlight_color if word.get('emphasis') or index == active else style.color
            if word.get('color') and word.get('emphasis'):
                color = word['color']
            top, bottom = font.getbbox(token)[1::2]
            draw_tracked(draw, (x, y+(line_height-(bottom-top))/2-top), token, font, tracking,
                         fill=color, stroke_width=style.stroke_width, stroke_fill=style.stroke_color)
            x += token_width
        y += line_height
    return image


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
