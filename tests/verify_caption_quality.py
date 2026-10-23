"""Opt-in comparison against the user's local Caption Engine sample and transcript."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import FFMPEG_PATH, EXPORT_DIR
from app.schemas.captions import EngineTranscript
from app.schemas.editing_plan import EditingPlan, ClipConfig, TitleConfig, SubtitleSegment
from app.services.caption_engine import readable_segments
from app.services.caption_documents import import_engine_transcript
from app.services.video_renderer import start_render_job, get_job_status

REFERENCE = Path(r'C:\Users\tejar\OneDrive\Desktop\New folder\caption-engine')
ART = ROOT / 'test_artifacts' / 'caption-quality'


def run(*args):
    return subprocess.check_output([FFMPEG_PATH, '-v', 'error', '-y', *map(str, args)], stderr=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    parser.add_argument('--source', default='media_292654431488b86e.mp4')
    parser.add_argument('--fresh', action='store_true', help='Use the actual Rayflow Medium inference artifact')
    args = parser.parse_args()
    ART.mkdir(parents=True, exist_ok=True)
    transcript = EngineTranscript.model_validate_json((REFERENCE / 'tmp/transcript.json').read_text(encoding='utf8'))
    subtitles = import_engine_transcript(transcript, args.source)
    if args.fresh:
        subtitles = readable_segments([SubtitleSegment.model_validate(row) for row in
                                      json.loads((ART/'medium-transcript.json').read_text(encoding='utf8'))])
    plan = EditingPlan(duration_seconds=24.6, aspect_ratio='9:16', style='minimal', color_strength=0,
                       title=TitleConfig(enabled=False), subtitles=subtitles, source_filename=args.source,
                       clips=[ClipConfig(id='reference-source', image_url=f'/api/uploads/{args.source}',
                                         media_type='video', start_time=0, duration=24.6, motion='static')])
    (ART / f'{args.phase}-plan.json').write_text(plan.model_dump_json(indent=2), encoding='utf8')
    started = time.monotonic()
    job_id = start_render_job(plan, [args.source])
    deadline = started + 300
    while time.monotonic() < deadline:
        job = get_job_status(job_id)
        if job.status in ('completed', 'failed'):
            break
        time.sleep(.25)
    assert job.status == 'completed', job.error
    video = EXPORT_DIR / f'rayflow_{job_id}.mp4'
    import shutil
    shutil.copyfile(video, ART / f'{args.phase}.mp4')
    run('-xerror', '-i', video, '-f', 'null', '-')
    for timestamp in [2.4, 8, 14]:
        run('-ss', timestamp, '-i', video, '-frames:v', 1, ART / f'{args.phase}-{timestamp}.png')
        if args.phase == 'after':
            sheet = Image.new('RGB', (1080, 690), '#151515')
            draw = ImageDraw.Draw(sheet)
            for index, label in enumerate(['reference', 'before', 'after']):
                image = Image.open(ART / f'{label}-{timestamp}.png').convert('RGB').resize((360, 640))
                sheet.paste(image, (index * 360, 30))
                draw.text((index * 360 + 10, 8), label, fill='white')
            sheet.save(ART / f'comparison-{timestamp}.png')
    print(json.dumps({'phase': args.phase, 'render_seconds': round(time.monotonic()-started, 2),
                      'duration': plan.duration_seconds, 'cues': len(subtitles), 'video': str(ART/f'{args.phase}.mp4')}), flush=True)


if __name__ == '__main__':
    main()
