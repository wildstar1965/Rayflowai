"""Explicit one-time downloads; never executed automatically by the application."""
import argparse
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent

def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix('.part')
    try:
        with requests.get(url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            with temp.open('wb') as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
        temp.replace(destination)
        print(destination.name, destination.stat().st_size, 'bytes')
    finally:
        temp.unlink(missing_ok=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', action='store_true')
    parser.add_argument('--segmentation', action='store_true')
    parser.add_argument('--video-matting', action='store_true')
    parser.add_argument('--whisper', metavar='MODEL', help='Explicitly cache a Faster-Whisper model, for example medium, small or large-v3')
    args = parser.parse_args()
    if args.whisper:
        from faster_whisper import WhisperModel
        WhisperModel(args.whisper, device='cpu', compute_type='int8', local_files_only=False)
        print('Whisper model cached for local inference.')
    if args.font:
        for name in ['Anton-Regular.ttf', 'OFL.txt']:
            download('https://raw.githubusercontent.com/google/fonts/main/ofl/anton/' + name, ROOT / 'assets/fonts' / name)
    if args.segmentation:
        download('https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx', ROOT / 'models/u2net_human_seg.onnx')
    if args.video_matting:
        download('https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx', ROOT / 'models/rvm_mobilenetv3_fp32.onnx')
