"""Repair the one-time source import, preserving all adapted workspace modules."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\tejar\OneDrive\Desktop\aieditor\ai-video-production-editor')
TARGET = ROOT / 'frontend/src/features/ai-editor'

# These are standalone website entry points, not editor tools or workspace code.
for name in ('agb.tsx', 'contact.tsx', 'landing-en.tsx', 'landing-fr.tsx', 'docs.tsx',
             'faq.tsx', 'datenschutz.tsx', 'portfolio.tsx', 'pricing.tsx', 'services.tsx',
             'software.tsx', 'widerruf.tsx', 'embed-host-demo.ts'):
    (TARGET / name).unlink(missing_ok=True)

relative = Path('sdk/storyProjectDefaults.ts')
(TARGET / relative).parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(SOURCE / 'src' / relative, TARGET / relative)
shutil.copytree(SOURCE / 'scripts/audio_mastering', ROOT / 'backend/editor-runtime/audio_mastering', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

manifest_path = ROOT / 'docs/ai-editor-source-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
for entry in manifest:
    if not (ROOT / entry['destination']).exists():
        entry['status'] = 'excluded: standalone website or payment functionality; not an editor workspace'
if not any(entry['source'] == 'src/' + relative.as_posix() for entry in manifest):
    manifest.append({'source': 'src/' + relative.as_posix(), 'destination': (TARGET / relative).relative_to(ROOT).as_posix(),
                     'sha256': hashlib.sha256((SOURCE / 'src' / relative).read_bytes()).hexdigest(),
                     'status': 'imported: shared Project workflow defaults; verification pending'})
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
