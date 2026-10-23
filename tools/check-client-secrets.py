"""Check built client files for configured secret values without printing those values."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    candidates = set()
    for folder in (ROOT, ROOT / 'backend', ROOT / 'frontend'):
        for source in folder.glob('.env*'):
            if 'example' in source.name or not source.is_file():
                continue
            for line in source.read_text(encoding='utf-8-sig').splitlines():
                match = re.match(r'\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)', line)
                if not match:
                    continue
                name, value = match.groups()
                if value[:1] in ('"', "'"):
                    quote = value[0]
                    value = value[1:].split(quote, 1)[0]
                else:
                    value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
                if value and len(value) >= 12 and re.search(r'key|token|password|secret', name, re.I):
                    candidates.add(value.encode())
    output = ROOT / 'frontend' / 'dist'
    files = [path for path in output.rglob('*') if path.is_file() and path.suffix in ('.js', '.mjs', '.css', '.html', '.json', '.map')]
    if not files:
        raise SystemExit('Build the frontend before scanning client artifacts.')
    hits = []
    for path in files:
        content = path.read_bytes()
        if any(value in content for value in candidates):
            hits.append(path.relative_to(ROOT).as_posix())
    if hits:
        print('Configured secret values were found in these client artifacts:')
        for path in hits:
            print(path)
        raise SystemExit(1)
    print(f'No configured secret values found in {len(files)} built client files ({len(candidates)} configured values checked).')
    print('This value scan does not replace source review or API/export isolation checks.')


if __name__ == '__main__':
    main()
