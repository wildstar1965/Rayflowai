"""Copy additional active upstream media runtimes, never writing to the source tree."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'aieditor' / 'ai-video-production-editor'
TARGET = ROOT / 'backend/editor-runtime'
for name in ('surface-map-runtime', 'corridor-key-runtime', 'corridor-key-utils'):
    source = SOURCE / 'electron' / (name + '.js')
    target = TARGET / (name + '.cjs')
    if target.exists():
        continue
    text = source.read_text(encoding='utf-8')
    text = text.replace("require('./surface-map-utils')", "require('./surface-map-utils.cjs')")
    text = text.replace("require('./corridor-key-utils')", "require('./corridor-key-utils.cjs')")
    text = text.replace("path.join(APP_ROOT, 'scripts', 'corridor_key_runner.py')", "path.join(__dirname, 'corridor_key_runner.py')")
    text = text.replace("['run', 'python', CORRIDOR_KEY_RUNNER_PATH", "['run', '--no-sync', 'python', CORRIDOR_KEY_RUNNER_PATH")
    target.write_text(text, encoding='utf-8')
target = TARGET / 'corridor_key_runner.py'
if not target.exists():
    target.write_bytes((SOURCE / 'scripts/corridor_key_runner.py').read_bytes())
