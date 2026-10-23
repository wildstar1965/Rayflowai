"""Script-aware Noto selection adapted from Caption Engine, using Pillow/RAQM."""
from functools import lru_cache
import unicodedata
from PIL import ImageFont, features
from app.core.config import ASSET_DIR
from app.services.cinematic import local_font

SCRIPT_FONTS = (
    (0x0900, 0x097F, 'Devanagari'), (0x0980, 0x09FF, 'Bengali'),
    (0x0A00, 0x0A7F, 'Gurmukhi'), (0x0A80, 0x0AFF, 'Gujarati'),
    (0x0B00, 0x0B7F, 'Oriya'), (0x0B80, 0x0BFF, 'Tamil'),
    (0x0C00, 0x0C7F, 'Telugu'), (0x0C80, 0x0CFF, 'Kannada'),
    (0x0D00, 0x0D7F, 'Malayalam'),
)


def script_for(text):
    return next((name for low, high, name in SCRIPT_FONTS if any(low <= ord(char) <= high for char in text)), '')


@lru_cache(maxsize=256)
def noto_font(size, script, weight):
    if script and not features.check_feature('raqm'):
        raise ValueError('Complex-script captions require a Pillow build with RAQM shaping. Install the current Pillow wheel.')
    filename = f'NotoSans{script}_{"700Bold" if weight >= 600 else "400Regular"}.ttf'
    path = ASSET_DIR / 'fonts' / 'caption-engine' / filename
    if not path.is_file():
        raise ValueError('The bundled caption font is missing. Restore backend/assets/fonts/caption-engine.')
    return ImageFont.truetype(str(path), max(1, round(size)))


def caption_font(text, size, family, weight):
    script = script_for(text)
    if script or family == 'Noto Sans':
        return noto_font(size, script, weight)
    return local_font(size, family, weight)


def script_runs(text):
    """Keep combining marks/joiners with their base; select fonts within a token.

    Adapted from Caption Engine text/script.ts and shaper.ts. Pillow's RAQM
    performs HarfBuzz shaping of each complete run, never individual Indic letters.
    """
    runs = []
    for char in text:
        script = script_for(char)
        if runs and (char in '\u200c\u200d' or unicodedata.category(char).startswith('M')):
            script = runs[-1][0]
        if runs and runs[-1][0] == script:
            runs[-1] = (script, runs[-1][1] + char)
        else:
            runs.append((script, char))
    return [run for _, run in runs]
