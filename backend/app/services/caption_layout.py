"""Caption Engine svg.ts layoutCue/resolveWordStyle adapted to Pillow/RAQM.

Stable reserved word slots, shared baselines, measured script runs, two outline/
fill passes. The editor and FFmpeg consume the very same raster output.
"""
from PIL import Image, ImageDraw
from app.services.caption_fonts import caption_font, script_runs
from app.services.cinematic import text_length, draw_tracked


def metrics(style, height):
    scale = height / 1920
    return style.font_size * scale, round(style.stroke_width * scale), style.tracking * scale


def shaped_runs(text, size, style, tracking):
    # Tracking individual codepoints breaks non-Latin clusters and ligatures.
    if any(ord(char) > 127 for char in text):
        tracking = 0
    runs, offset = [], 0
    for text_run in script_runs(text):
        font = caption_font(text_run, size, style.font_family, style.font_weight)
        advance = text_length(text_run, font, tracking)
        runs.append({'text': text_run, 'font': font, 'offset': offset, 'tracking': tracking})
        offset += advance
    return runs, offset


def layout_words(words, style, width, height):
    size, stroke, tracking = metrics(style, height)
    margin = width * .07 + stroke + 1
    usable = width - 2 * margin
    while True:
        font = caption_font(' ', size, style.font_family, style.font_weight)
        space = max(font.getlength(' '), size * .34) + tracking
        lines, current, used = [], [], 0
        for index, word in enumerate(words):
            for token_index, token in enumerate(word['word'].split()):
                resting, base_width = shaped_runs(token, size, style, tracking)
                active, active_width = shaped_runs(token, size * style.active_scale, style, tracking)
                slot = max(base_width, active_width) if style.highlight_active else base_width
                gap = 0 if word.get('join_left') and token_index == 0 else space
                if current and (used + gap + slot > usable or (word.get('line_before') and token_index == 0)):
                    lines.append((current, used))
                    current, used = [], 0
                gap = gap if current else 0
                current.append({'index': index, 'word': word, 'text': token, 'resting': resting,
                                'active': active, 'base_width': base_width, 'active_width': active_width,
                                'slot': slot, 'offset': used + gap})
                used += slot + gap
        if current:
            lines.append((current, used))
        line_height = size * 1.38
        if size <= 1 or (all(length <= usable for _, length in lines)
                         and len(lines) <= 2 and len(lines) * line_height <= height * .8):
            break
        size = max(1, size - max(.5, size * .04))
    anchor = height * (.12 if style.position == 'top' else .5 if style.position == 'middle'
                       else .72 if style.safe_area else .86)
    baseline = anchor - len(lines) * line_height / 2 + size * .5
    output, bounds = [], []
    for line_index, (line, length) in enumerate(lines):
        left = margin if style.alignment == 'left' else width-margin-length if style.alignment == 'right' else (width-length)/2
        for item in line:
            item = {**item, 'x': left + item['offset'], 'baseline': baseline + line_index * line_height}
            output.append(item)
            # Reserve the union of resting/active ink, not the current highlight.
            for state in ['resting', 'active'] if style.highlight_active else ['resting']:
                advance = item['active_width' if state == 'active' else 'base_width']
                for run in item[state]:
                    l, t, r, b = run['font'].getbbox(run['text'], anchor='ls')
                    x = item['x'] + (item['slot']-advance)/2 + run['offset']
                    bounds.append((x+l-stroke, item['baseline']+t-stroke,
                                   x+r+stroke, item['baseline']+b+stroke))
    if bounds:
        top, bottom = min(b[1] for b in bounds), max(b[3] for b in bounds)
        shift = max(0, height*.05-top) - max(0, bottom-height*.95)
        for item in output:
            item['baseline'] += shift
        bounds = [(l, t+shift, r, b+shift) for l,t,r,b in bounds]
    return output, bounds, size, stroke


def paint_caption(words, style, width, height, active=None):
    items, bounds, size, stroke = layout_words(words, style, width, height)
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)
    if style.background_opacity and bounds:
        pad = size*.25
        box = (max(0, min(b[0] for b in bounds)-pad), max(0, min(b[1] for b in bounds)-pad),
               min(width, max(b[2] for b in bounds)+pad), min(height, max(b[3] for b in bounds)+pad))
        draw.rounded_rectangle(box, radius=size*.2,
            fill=tuple(int(style.background_color[i:i+2],16) for i in (1,3,5))+(round(255*style.background_opacity),))
    for outline_pass in [True, False]:
        for item in items:
            is_active = item['index'] == active and style.highlight_active
            state = 'active' if is_active else 'resting'
            advance = item['active_width' if is_active else 'base_width']
            color = style.highlight_color if is_active else style.color
            if not style.highlight_active and item['word'].get('emphasis'):
                color = item['word'].get('color') or style.highlight_color
            for run in item[state]:
                x = item['x'] + (item['slot']-advance)/2 + run['offset']
                draw_tracked(draw, (x, item['baseline']), run['text'], run['font'], run['tracking'],
                             anchor='ls', fill=style.stroke_color if outline_pass else color,
                             stroke_width=stroke if outline_pass else 0, stroke_fill=style.stroke_color)
    return image
