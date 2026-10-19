"""Opt-in live provider check; no credentials or exception URLs are printed."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.pixabay import search, download, MediaProviderError

if __name__ == '__main__':
    try:
        results = search('mountains', 'video', '9:16')
        if not results:
            raise MediaProviderError('No mountain video results returned.')
        asset = download(results[0]['id'], 'video')
        record = {'query': 'mountains', 'results': len(results), 'asset_id': asset['id'],
                  'url': asset['url'], 'source_page': asset['source_page'], 'duration': asset['duration']}
        Path('test_artifacts/pixabay-live.json').write_text(json.dumps(record, indent=2), encoding='utf8')
        print(json.dumps(record))
    except MediaProviderError as exc:
        print(str(exc))
        sys.exit(1)
