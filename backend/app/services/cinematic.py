"""Local fonts and frame-exact typography shared by preview and FFmpeg."""
import hashlib
import json
import math
import re
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from app.core.config import ASSET_DIR, CACHE_DIR
from app.schemas.editing_plan import CinematicText

FPS = 30
_TITLE_LOCK = threading.Lock()


@lru_cache(maxsize=128)
def local_font(size, family='Anton', weight=700):
    windows = Path('C:/Windows/Fonts')
    linux = Path('/usr/share/fonts/truetype/dejavu')
    choices = {
        'Anton': [ASSET_DIR / 'fonts/Anton-Regular.ttf', windows / 'impact.ttf', linux / 'DejaVuSansCondensed-Bold.ttf'],
        'Arial': [windows / ('arialbd.ttf' if weight >= 600 else 'arial.ttf'), linux / ('DejaVuSans-Bold.ttf' if weight >= 600 else 'DejaVuSans.ttf')],
        'DejaVu Sans': [linux / ('DejaVuSans-Bold.ttf' if weight >= 600 else 'DejaVuSans.ttf'), windows / ('arialbd.ttf' if weight >= 600 else 'arial.ttf')],
        'Trebuchet MS': [windows / ('trebucbd.ttf' if weight >= 600 else 'trebuc.ttf')],
    }
    paths = choices.get(family.split(',')[0], choices['Arial'])
    for path in paths + choices['Arial'] + choices['Anton']:
        if path.is_file():
            return ImageFont.truetype(str(path), max(1, round(size)))
    return ImageFont.load_default(size=max(1, round(size)))


def display_font(size):
    return local_font(size)


def text_length(text, font, tracking=0):
    return font.getlength(text) + max(0, len(text)-1)*tracking


def draw_tracked(draw, xy, text, font, tracking=0, **kwargs):
    if not tracking:
        draw.text(xy, text, font=font, **kwargs)
        return
    x, y = xy
    for index, char in enumerate(text):
        offset = font.getlength(text[:index+1])-font.getlength(char)+index*tracking
        draw.text((x+offset, y), char, font=font, **kwargs)


def animation_state(title, frame):
    total = max(1, round(title.duration*FPS))
    fade = min(title.animation_seconds, title.duration/3)
    time = frame/FPS
    alpha = 1 if not fade else max(0, min(1, time/fade, (total/FPS-time)/fade))
    progress = 1 if not fade else max(0, min(1, time/fade))
    scale = title.scale_from+(1-title.scale_from)*(1-(1-progress)**3)
    return float(round(alpha, 6)), float(round(scale, 6))


def title_image(text, color, width, height, title=None, frame=None):
    title = title or CinematicText(id='raster', text=text, color=color, start_time=0, duration=2.5, source_clip_id='raster')
    fields = title.model_dump(exclude={'id', 'source_clip_id', 'origin', 'behind_subject', 'start_time', 'duration'})
    state = animation_state(title, frame) if frame is not None else (1.0, 1.0)
    key = hashlib.sha256(json.dumps(['type-v4', fields, width, height, state], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f'type_{key}.png'
    with _TITLE_LOCK:
        if not path.exists():
            image = _paint_title(title, width, height)
            alpha, scale = state
            if scale != 1:
                scaled = image.resize((round(width*scale), round(height*scale)), Image.Resampling.LANCZOS)
                image = Image.new('RGBA', (width, height))
                image.paste(scaled, ((width-scaled.width)//2, (height-scaled.height)//2))
            if alpha != 1:
                image.putalpha(image.getchannel('A').point(lambda value: round(value*alpha)))
            atomic_png(image, path)
    return path


def atomic_png(image, path):
    temp = path.with_suffix(f'.{uuid.uuid4().hex}.tmp.png')
    try:
        image.save(temp)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _paint_title(title, width, height):
    text = title.text.upper() if title.uppercase else title.text
    size = max(10, round(width*title.font_size_ratio))
    tracking = title.tracking*width/1080
    margin = math.ceil(width*.055)
    usable = width-2*margin
    while True:
        font = local_font(size, title.font_family, title.font_weight)
        lines = []
        for paragraph in text.split('\n'):
            line = ''
            for word in paragraph.split():
                candidate = (line+' '+word).strip()
                if line and text_length(candidate, font, tracking) > usable:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        block_height = len(lines)*size*1.08
        if size <= 10 or (max((text_length(line, font, tracking) for line in lines), default=0) <= usable
                          and block_height <= height*.45):
            break
        size -= 2
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)
    y = min(max(height*.05, height*title.y), height*.95-block_height)
    emphasis = {word.casefold().strip('.,!?') for word in title.emphasis_words}
    for line in lines:
        length = text_length(line, font, tracking)
        anchor = width*title.x
        x = anchor-(length/2 if title.alignment == 'center' else length if title.alignment == 'right' else 0)
        x = max(margin, min(x, width-margin-length))
        top = font.getbbox(line or 'A')[1]
        prefix = ''
        for token in line.split(' '):
            color = title.highlight_color if token.casefold().strip('.,!?') in emphasis else title.color
            offset = font.getlength(prefix)+len(prefix)*tracking
            draw_tracked(draw, (x+offset, y-top), token, font, tracking, fill=color,
                         stroke_width=max(1, width//600), stroke_fill='#25201a')
            prefix += token+' '
        y += size*1.08
    return image


def write_frame_track(paths, destination, fps=FPS):
    """One lossless PNG stream with explicit frame ticks, instead of hundreds of inputs."""
    lines = ['ffconcat version 1.0']
    previous, count = None, 0

    def append(path, ticks):
        escaped = Path(path).resolve().as_posix().replace("'", "'\\''")
        lines.extend([f"file '{escaped}'", f'option framerate {fps}', f'duration {ticks/fps:.9f}'])

    for path in paths:
        if previous is not None and path != previous:
            append(previous, count)
            count = 0
        previous = path
        count += 1
    if previous is not None:
        append(previous, count)
        append(previous, 1)
    Path(destination).write_text('\n'.join(lines)+'\n', encoding='utf8')
    return str(destination)


def title_track(title, width, height, destination, check=None):
    def frames():
        for frame in range(max(1, round(title.duration*FPS))):
            if check:
                check()
            yield title_image(title.text, title.color, width, height, title, frame)
    return write_frame_track(frames(), destination)


def suggest_cinematic_texts(plan):
    if not plan.subtitles or not plan.clips:
        return []
    candidates = [s for s in plan.subtitles if len(s.text.split()) >= 3 and s.end_time-s.start_time >= .6
                  and not re.match(r'^(hi|hello|hey|thanks|thank you)\b', s.text.strip(), re.I)]
    if not candidates:
        return []
    first = next((s for s in candidates if any(w.emphasis for w in s.words)), candidates[0])
    clip = next((c for c in plan.clips if c.start_time <= first.start_time < c.start_time+c.duration), None)
    if not clip:
        return []
    selected = first.words[:6]
    text = ' '.join(first.text.split()[:6]).strip(' ,.!?')
    if not text:
        return []
    end = selected[-1].end if selected else first.end_time
    return [CinematicText(id='opening-'+first.id, text=text, start_time=first.start_time,
                duration=min(2.5, end-first.start_time, clip.start_time+clip.duration-first.start_time),
                source_clip_id=clip.id, behind_subject=False, origin='auto',
                emphasis_words=[w.word for w in selected if w.emphasis])]
