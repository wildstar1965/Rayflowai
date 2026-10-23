"""Portable subtitle documents; plain text formats never contain HTML/ASS markup."""
import html
import json
from app.schemas.editing_plan import SubtitleSegment, SubtitleStyle
from app.services.caption_engine import cue_windows, validate_captions
from app.services.caption_frames import caption_units
from app.services.caption_layout import metrics
from app.services.subtitles import format_ass_time, hex_to_ass_color


def import_engine_transcript(transcript, filename, use_roman=False):
    if not transcript.hasWordTimings:
        raise ValueError('This transcript has no genuine word timestamps. Import a word-timed transcript.')
    words, cursor = [], 0.0
    for word in transcript.words:
        if word.end < word.start or word.end > transcript.duration + .001:
            raise ValueError('Transcript word times must fit inside its duration.')
        if word.type != 'word' or not word.keep or not word.text.strip():
            continue
        if word.start < cursor - .000001 or word.end <= word.start:
            raise ValueError('Spoken words must have positive, ordered, non-overlapping timestamps.')
        text = word.roman if use_roman and word.roman else word.text
        words.append({'word': text, 'start': word.start, 'end': word.end,
                      'confidence': word.confidence, 'speaker_id': word.speakerId,
                      'language': word.language or transcript.language})
        cursor = word.end
    style = SubtitleStyle(caption_mode='phrase', highlight_active=True, safe_area=True)
    subtitles = [SubtitleSegment(id=f'import-{index}', text=' '.join(w['word'] for w in group),
                                start_time=start, end_time=end, words=group, style=style,
                                source_filename=filename, origin='auto')
                 for index, (start, end, group) in enumerate(cue_windows(words, style, 0, transcript.duration))]
    return validate_captions(subtitles, transcript.duration)


def timestamp(milliseconds, separator='.'):
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, ms = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{ms:03}'


def unit_text(words):
    output = ''
    for word in words:
        output += ('\n' if word.get('line_before') else '' if not output or word.get('join_left') else ' ') + word['word']
    return output


def plain_cues(segments):
    cues = []
    for segment in segments:
        # Highlight changes don't split SRT/VTT into repeated copies of a phrase.
        previous = None
        for start, end, words, _ in caption_units(segment, segment.end_time):
            text = unit_text(words)
            if previous and previous[2] == text and abs(previous[1] - start) < .000001:
                previous[1] = end
            else:
                previous = [start, end, text]
                cues.append(previous)
    return cues


def export_document(document, fmt, width=1080, height=1920):
    if fmt == 'json':
        return json.dumps(document.model_dump(), ensure_ascii=False, indent=2) + '\n'
    if fmt == 'ass':
        return build_ass(document.subtitles, width, height)
    lines = ['WEBVTT', ''] if fmt == 'vtt' else []
    previous_end = 0
    index = 0
    for start, end, text in plain_cues(document.subtitles):
        begin_ms, end_ms = max(previous_end, round(start * 1000)), round(end * 1000)
        if end_ms <= begin_ms:
            continue
        previous_end = end_ms
        # Blank lines terminate a cue, and markup must remain literal text.
        text = html.escape(text.replace('\r', '').replace('\x00', ''), quote=False)
        text = '\n'.join(line for line in text.split('\n') if line.strip())
        index += 1
        separator = ',' if fmt == 'srt' else '.'
        lines.extend([str(index), f'{timestamp(begin_ms, separator)} --> {timestamp(end_ms, separator)}', text, ''])
    return '\n'.join(lines) + '\n'


def build_ass(segments, width, height):
    """Use the same phrase windows and active-word states as Rayflow's renderer."""
    styles, events = [], []

    def safe(text):
        return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\r', '').replace('\n', r'\N')

    for index, segment in enumerate(segments):
        style = segment.style or SubtitleStyle()
        font_size, stroke_width, tracking = metrics(style, height)
        name = f'Caption{index}'
        family = style.font_family.split(',')[0]
        color, outline = hex_to_ass_color(style.color), hex_to_ass_color(style.stroke_color)
        background = hex_to_ass_color(style.background_color + f'{round(style.background_opacity*255):02X}')
        align = {'left': 4, 'center': 5, 'right': 6}[style.alignment]
        x = width * (.08 if style.alignment == 'left' else .92 if style.alignment == 'right' else .5)
        y = height * (.12 if style.position == 'top' else .5 if style.position == 'middle' else .72 if style.safe_area else .86)
        styles.append(f'Style: {name},{family},{font_size},{color},{color},{outline},{background},'
                      f'{-1 if style.font_weight >= 600 else 0},0,0,0,100,100,{tracking},0,'
                      f'{3 if style.background_opacity else 1},{stroke_width},0,{align},0,0,0,1')
        for start, end, words, active in caption_units(segment, segment.end_time):
            if round(end * 100) <= round(start * 100):
                continue
            rendered = []
            for word_index, word in enumerate(words):
                prefix = r'\N' if word.get('line_before') else '' if not rendered or word.get('join_left') else ' '
                emphasis = active == word_index if style.highlight_active else word.get('emphasis')
                tint = hex_to_ass_color(style.highlight_color if style.highlight_active else word.get('color') or style.highlight_color) if emphasis else color
                text = word['word']
                size = font_size
                rendered.append(prefix + f'{{\\c{tint}\\fs{size:.2f}}}' + safe(text))
            position = f'{{\\an{align}\\pos({x:.1f},{y:.1f})}}'
            events.append(f'Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},{name},,0,0,0,,{position}{"".join(rendered)}')
    return '\n'.join([
        '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
        'ScaledBorderAndShadow: yes', '', '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        *styles, '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text', *events, '',
    ])
