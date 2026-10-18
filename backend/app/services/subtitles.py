import os
import re
from pathlib import Path
from typing import List, Optional
from app.schemas.editing_plan import SubtitleSegment, SubtitleStyle, WordTiming

def hex_to_ass_color(hex_str: Optional[str], default: str = "&H00FFFFFF&") -> str:
    """
    Converts #RRGGBB or #RRGGBBAA hex color to ASS format &HAABBGGRR&.
    Note: ASS uses BGR order, not RGB.
    """
    if not hex_str:
        return default
    c = hex_str.lstrip('#').strip()
    if len(c) == 6:
        r, g, b = c[0:2], c[2:4], c[4:6]
        return f"&H00{b}{g}{r}&".upper()
    elif len(c) == 8:
        r, g, b, a = c[0:2], c[2:4], c[4:6], c[6:8]
        # In ASS alpha: 00 = opaque, FF = fully transparent. Hex RGBA often has FF = opaque.
        # So invert alpha or map FF -> 00.
        ass_a = f"{255 - int(a, 16):02X}"
        return f"&H{ass_a}{b}{g}{r}&".upper()
    return default

def format_ass_time(seconds: float) -> str:
    """Formats seconds into ASS timestamp H:MM:SS.cs"""
    seconds = max(0.0, float(seconds))
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

# Curated Presets configuration
PRESET_CONFIGS = {
    "bold_pop": {
        "font_family": "Arial",
        "font_size_ratio": 0.048,  # Relative to video height for 9:16 (~92px on 1080x1920)
        "color": "#FFFFFF",
        "highlight_color": "#FACC15",  # Vibrant Yellow
        "stroke_color": "#000000",
        "stroke_width": 5,
        "bold": -1,
        "shadow": 2,
        "caption_mode": "word_by_word",
    },
    "fitness_energy": {
        "font_family": "Trebuchet MS",
        "font_size_ratio": 0.052,
        "color": "#38BDF8",  # Electric Cyan
        "highlight_color": "#F59E0B",  # Amber Glow
        "stroke_color": "#000000",
        "stroke_width": 6,
        "bold": -1,
        "shadow": 3,
        "caption_mode": "word_by_word",
    },
    "minimalist": {
        "font_family": "Arial",
        "font_size_ratio": 0.038,
        "color": "#F3F4F6",
        "highlight_color": "#E11D48",  # Crimson Accent
        "stroke_color": "#111827",
        "stroke_width": 3,
        "bold": -1,
        "shadow": 1,
        "caption_mode": "phrase",
    },
    "subtle_border": {
        "font_family": "Arial",
        "font_size_ratio": 0.040,
        "color": "#FFFFFF",
        "highlight_color": "#10B981",  # Emerald Green
        "stroke_color": "#1F2937",
        "stroke_width": 4,
        "bold": 0,
        "shadow": 1,
        "caption_mode": "phrase",
    }
}

def generate_ass_subtitles(
    subtitles: List[SubtitleSegment], output_ass_path: str,
    video_width: int = 1080, video_height: int = 1920,
) -> str:
    """Export each segment's actual style and timing, without overlapping words."""
    styles = []
    events = []
    def safe(text):
        return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", r"\N")
    for index, segment in enumerate(subtitles):
        style = segment.style or SubtitleStyle()
        preset = PRESET_CONFIGS.get(style.preset, PRESET_CONFIGS["bold_pop"])
        name = f"Caption{index}"
        size = style.font_size
        color = hex_to_ass_color(style.color)
        highlight = hex_to_ass_color(style.highlight_color)
        outline = hex_to_ass_color(style.stroke_color)
        margin = int(video_width * 0.08)
        family = style.font_family.split(",")[0].strip() or "Arial"
        styles.append(
            f"Style: {name},{family},{size},{color},&H000000FF&,{outline},&H80000000&,"
            f"{preset['bold']},0,0,0,100,100,0,0,1,{style.stroke_width},{preset['shadow']},"
            f"5,{margin},{margin},0,1"
        )
        y = video_height * (0.12 if style.position == "top" else 0.5 if style.position == "middle" else 0.86)
        position = f"{{\\an5\\pos({video_width / 2:.1f},{y:.1f})}}"
        if style.caption_mode == "word_by_word" and segment.words:
            for word_index, word in enumerate(segment.words):
                start = max(segment.start_time, word.start)
                next_start = segment.words[word_index + 1].start if word_index + 1 < len(segment.words) else segment.end_time
                end = min(segment.end_time, word.end, next_start)
                if end <= start or not word.word.strip():
                    continue
                text = safe(word.word.upper() if word.emphasis else word.word)
                tags = f"{{\\c{highlight}\\fs{size * 1.15:.1f}\\b1}}" if word.emphasis else ""
                events.append(f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},{name},,0,0,0,,{position}{tags}{text}")
        else:
            words = []
            for word in segment.words:
                text = safe(word.word)
                words.append(f"{{\\c{highlight}\\b1}}{text}{{\\r{name}}}" if word.emphasis else text)
            text = " ".join(words) if words else safe(segment.text)
            if segment.end_time > segment.start_time:
                events.append(f"Dialogue: 0,{format_ass_time(segment.start_time)},{format_ass_time(segment.end_time)},{name},,0,0,0,,{position}{text}")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {video_width}", f"PlayResY: {video_height}",
        "ScaledBorderAndShadow: yes", "WrapStyle: 0", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, "",
    ]
    Path(output_ass_path).write_text("\n".join(lines), encoding="utf-8")
    return output_ass_path
