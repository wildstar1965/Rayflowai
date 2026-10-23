"""Import the active upstream source without modifying the source repository.

Run once when updating the vendored baseline; subsequent integration edits live
in Rayflow. The manifest records provenance and every upstream module.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\tejar\OneDrive\Desktop\aieditor\ai-video-production-editor')
TARGET = ROOT / 'frontend/src/features/ai-editor'


def main():
    if TARGET.exists():
        raise SystemExit('The editor has already been imported; do not overwrite integration changes.')
    TARGET.mkdir(parents=True)
    manifest = []
    for source in sorted((SOURCE / 'src').rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(SOURCE / 'src')
        # Web entrypoints and the separate marketing/portal apps are not mounted.
        if relative.parts[0] in ('landing', 'portal', 'sdk') or str(relative) in ('index.tsx', 'landing.tsx', 'embed.tsx', 'portal.tsx'):
            continue
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        text = source.read_text(encoding='utf-8', errors='replace') if source.suffix in ('.ts', '.tsx', '.js') else ''
        manifest.append({'source': 'src/' + relative.as_posix(), 'destination': destination.relative_to(ROOT).as_posix(),
                         'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                         'exports': re.findall(r'export\s+(?:async\s+)?(?:const|function|class|interface|type)\s+(\w+)', text),
                         'status': 'imported; integration verification pending'})
    for name in ('LICENSE', 'NOTICE', 'AUTHORS.md'):
        shutil.copyfile(SOURCE / name, TARGET / name)
    shutil.copyfile(SOURCE / 'index.css', TARGET / 'upstream.css')
    runtime = ROOT / 'backend/editor-runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ('ffmpeg-handler.js', 'audio-mastering-utils.js', 'audio-remaster-utils.js', 'surface-map-utils.js'):
        shutil.copyfile(SOURCE / 'electron' / name, runtime / name.replace('.js', '.cjs'))
    for name in ('audio_mastering_worker.py', 'audio_remaster_worker.py'):
        shutil.copyfile(SOURCE / 'scripts' / name, runtime / name)
    (ROOT / 'docs/ai-editor-source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(manifest)} active source modules with upstream notices.')


if __name__ == '__main__':
    main()
