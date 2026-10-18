"""Decode and inspect a real export; writes a contact sheet and JSON evidence."""
import json
import re
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import FFMPEG_PATH

path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'test_artifacts/browser-auto-reel.mp4'
decoded = subprocess.run([FFMPEG_PATH, '-hide_banner', '-xerror', '-i', str(path),
    '-vf', 'showinfo', '-f', 'null', '-'], capture_output=True, text=True)
assert decoded.returncode == 0, decoded.stderr[-2000:]
pts = [float(t) for t in re.findall(r'\bn:\s*\d+\s+pts:\s*\d+\s+pts_time:([\d.e+-]+)', decoded.stderr)]
assert pts and np.allclose(np.diff(pts), 1 / 30, atol=0.0001), 'Non-uniform frame timestamps'
probe = decoded.stderr
resolution = re.search(r'Video: h264[^\n]*? (\d{3,4})x(\d{3,4})', probe)
assert resolution
raw = subprocess.run([FFMPEG_PATH, '-v', 'error', '-i', str(path), '-vf', 'fps=1,scale=320:180',
    '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 180, 320, 3)
sheet = Image.new('RGB', (320 * 4, 204 * ((len(frames) + 3) // 4)), 'white')
draw = ImageDraw.Draw(sheet)
for i, frame in enumerate(frames):
    x, y = i % 4 * 320, i // 4 * 204
    sheet.paste(Image.fromarray(frame), (x, y))
    draw.text((x + 5, y + 184), f'{i}s', fill='black')
sheet.save(path.with_suffix('.contact.png'))
report = {'path': str(path), 'duration_seconds': round(len(pts) / 30, 6),
          'width': int(resolution[1]), 'height': int(resolution[2]), 'fps': 30,
          'frame_count': len(pts), 'uniform_timestamps': True, 'full_decode': True,
          'video_codec': 'H.264', 'audio_stream': 'AAC' if 'Audio: aac' in probe else 'none'}
plan_file = path.parent / 'browser-plan.json'
if plan_file.exists() and path.name == 'browser-auto-reel.mp4':
    expected = json.loads(plan_file.read_text(encoding='utf8'))['duration_seconds']
    assert len(pts) == round(expected * 30), f'Expected {round(expected * 30)} frames, got {len(pts)}'
path.with_suffix('.inspection.json').write_text(json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report, indent=2))
