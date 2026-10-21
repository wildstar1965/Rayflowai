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
    key = hashlib.sha256(json.dumps(['type-v5', fields, width, height, state], sort_keys=True).encode()).hexdigest()
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
            rgb = tuple(int(color[i:i+2],16) for i in (1,3,5))
            outline = '#EAE5DC' if sum(rgb)/3 < 110 else '#25201a'
            offset = font.getlength(prefix)+len(prefix)*tracking
            draw_tracked(draw, (x+offset, y-top), token, font, tracking, fill=color,
                         stroke_width=max(1, width//540), stroke_fill=outline)
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
    """Choose complete, transcript-grounded phrases; never truncate to six words."""
    candidates = []
    stop = {'i', 'we', 'my', 'our', 'the', 'a', 'an', 'to', 'and', 'or', 'but', 'at', 'from',
            'in', 'on', 'of', 'is', 'am', 'are', 'it', 'this', 'that', 'you', 'your', 'various'}
    for segment in plan.subtitles or plan.transcript:
        text = segment.text.strip()
        sentences = re.split(r'[.;!?]', text)
        phrases = sentences + [sentence.split(',')[0] for sentence in sentences if ',' in sentence]
        # A prepositional subject often makes a useful display phrase in an introduction.
        phrases += re.findall(r'\b(?:from|about|across)\s+(.+?)(?:\s+at\s|[.!?]|$)', text, re.I)
        for phrase in phrases:
            phrase = re.sub(r'^(?:coming to|moving on to|let us talk about|let.s talk about)\s+(?:(?:my|our|the)\s+)?', '', phrase.strip(), flags=re.I)
            tokens = phrase.split()
            clean = [re.sub(r'[^\w]', '', word.casefold()) for word in tokens]
            if not 2 <= len(tokens) <= 8 or clean[-1] in stop or len(phrase)>72:
                continue
            if clean[0] in {'hi','hello','hey','thanks','thank'} or sum(w not in stop for w in clean)<2:
                continue
            # Don't excerpt away a qualification or negation.
            if re.search(r"\b(?:not|never|no|without|unless|don.t|can.t|isn.t)\b", text, re.I) and phrase not in [text.rstrip('.!?')]:
                continue
            source = [re.sub(r'[^\w]', '', w.word.casefold()) for w in segment.words]
            offset = next((i for i in range(len(source)-len(clean)+1) if source[i:i+len(clean)] == clean), None)
            if offset is None:
                if segment.words or phrase != text.rstrip('.!?'):
                    continue
                start,end = segment.start_time,segment.end_time
            else:
                selected = segment.words[offset:offset+len(clean)]
                start,end = selected[0].start,selected[-1].end
            if end-start<.65:
                continue
            clip = next((c for c in plan.clips if c.start_time<=start<c.start_time+c.duration),None)
            if not clip:
                continue
            finish = min(clip.start_time+clip.duration,end+.16,plan.duration_seconds)
            if finish-start<.65:
                continue
            candidates.append((start,finish,phrase,clip,segment.id))
    titles=[]
    for start,end,text,clip,identity in sorted(candidates,key=lambda row:(row[0],len(row[2]))):
        if len(titles)>=3 or any(start<t.start_time+t.duration+2 for t in titles):
            continue
        if any(start<i.start_time+i.duration and end>i.start_time for i in plan.visual_inserts):
            continue
        tokens=text.split()
        font=local_font(108)
        # Balance two lines, with conjunctions kept with the preceding words.
        splits=[i for i in range(1,len(tokens)) if tokens[i].lower() not in {'and','or','of'}]
        split=min(splits,key=lambda i:max(font.getlength(' '.join(tokens[:i]).upper()),font.getlength(' '.join(tokens[i:]).upper()))) if splits else 0
        lines=[' '.join(tokens[:split]),' '.join(tokens[split:])] if split else [text]
        widest=max(font.getlength(line.upper()) for line in lines)
        ratio=min(.16,.1*940/max(1,widest))
        if ratio<.11 and len(splits)>=2:
            from itertools import combinations
            first,second=min(combinations(splits,2),key=lambda pair:max(
                font.getlength(' '.join(part).upper()) for part in
                (tokens[:pair[0]],tokens[pair[0]:pair[1]],tokens[pair[1]:])))
            lines=[' '.join(tokens[:first]),' '.join(tokens[first:second]),' '.join(tokens[second:])]
            widest=max(font.getlength(line.upper()) for line in lines)
            ratio=min(.14,.1*940/max(1,widest))
        emphasis=max(tokens,key=lambda token:len(token.strip(',.'))).strip(',.')
        titles.append(CinematicText(id='display-'+identity+'-'+str(len(titles)),text='\n'.join(lines),
            start_time=start,duration=min(2.8,end-start),source_clip_id=clip.id,origin='auto',
            font_size_ratio=max(.06,ratio),y=.065,tracking=.2,emphasis_words=[emphasis],
            animation_seconds=.12,scale_from=.985))
    return titles


def place_title_with_mattes(title, mattes):
    """Use sampled real mattes to keep at least 72% of a generated heading visible."""
    import numpy as np
    width,height=mattes[0].size
    masks=[np.asarray(matte,dtype=float)/255 for matte in mattes]
    choices=[]
    for y in [.065,.09,.12,.15,.18]:
        candidate=title.model_copy(update={'y':y})
        alpha=np.asarray(_paint_title(candidate,width,height).getchannel('A'),dtype=float)/255
        overlaps=[float((alpha*mask).sum()/max(1,alpha.sum())) for mask in masks]
        if max(overlaps)<=.28:
            choices.append((abs(sum(overlaps)/len(overlaps)-.09),y))
    title.y=min(choices)[1] if choices else .05
    title.behind_subject=bool(choices)


def choose_title_palette(title, clip, ratio, fit_mode):
    """Choose light/dark display ink from the actual source's upper composition."""
    import subprocess
    import numpy as np
    from app.core.config import FFMPEG_PATH
    from app.services.media import uploaded_path
    width,height={'9:16':(180,320),'1:1':(240,240),'16:9':(320,180)}[ratio]
    scale = (f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}' if fit_mode=='fill' else
             f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2')
    try:
        raw=subprocess.check_output([FFMPEG_PATH,'-v','error','-ss',str(clip.source_start+title.start_time-clip.start_time+title.duration/2),
            '-i',str(uploaded_path(clip.image_url)),'-frames:v','1','-vf',scale,'-f','rawvideo','-pix_fmt','rgb24','-'],
            timeout=20,stderr=subprocess.DEVNULL)
        pixels=np.frombuffer(raw,np.uint8).reshape(height,width,3)[round(height*.05):round(height*.25)]
        luma=pixels@np.array([.2126,.7152,.0722])
        if float(np.median(luma))>165:
            title.color='#29251F'
            title.highlight_color='#86451F'
    except (OSError,ValueError,subprocess.SubprocessError):
        pass  # Optional contrast sampling must not discard an otherwise usable draft.
