"""Validated bridge to reused media/SDK workers; credentials travel over stdin."""
import copy
import json
import math
import os
import subprocess
import sys
import threading
import signal
import shutil
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from .context import owner
from .providers import credential
from .store import store, safe_relative

RUNTIME = Path(__file__).resolve().parents[2] / 'editor-runtime'


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()


def validate_sdk(value):
    """Do not let SDK configuration override server-owned credentials or transport."""
    if isinstance(value, dict):
        if any(key in value for key in ('httpOptions', 'baseUrl', 'apiKey', 'uploadUrl', 'downloadPath', 'vertexai', 'googleAuthOptions')):
            raise ValueError('Google transport configuration is owned by the backend.')
        for child in value.values():
            validate_sdk(child)
    elif isinstance(value, list):
        for child in value:
            validate_sdk(child)


def mix_timeline_audio(output, project, identity, cancel):
    """The upstream HQ compositor renders video only; mux the owned timeline audio."""
    from app.core.config import FFMPEG_PATH
    from app.services.media import probe_media
    from .audio_automation import volume_filter
    tracks = {track['id']: track for track in project.get('timelineTracks', [])}
    media = {item['id']: item for item in project.get('mediaItems', [])}
    solo = {kind: any(track.get('type') == kind and track.get('isSolo') for track in tracks.values()) for kind in ('audio', 'video')}
    command = [str(FFMPEG_PATH), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(output)]
    filters = []
    for clip in project.get('timelineClips', []):
        item = media.get(clip.get('mediaId'), {})
        if item.get('type') not in ('audio', 'video'):
            continue
        track = tracks.get(clip.get('trackId'), {})
        kind = 'audio' if item.get('type') == 'audio' else 'video'
        if track.get('isMuted') or (solo[kind] and not track.get('isSolo')):
            continue
        source = media_path(item.get('url'))
        info = probe_media(source)
        if not info.get('has_audio'):
            continue
        if any(frame.get('property') == 'pan' for frame in clip.get('keyframes', [])) or clip.get('audioEffects'):
            raise ValueError('This audio effect is not supported by backend export. Render the effect into an audio asset first. Quick browser export records video only.')
        start = max(0, float(clip.get('start', 0)))
        end = float(clip.get('end', start))
        speed = max(0.05, min(20, float(clip.get('speed') or 1)))
        source_in = max(0, float(clip.get('sourceIn') or 0))
        source_out = float(clip.get('sourceOut') or (source_in + (end - start) * speed))
        volume = max(0, min(8, float(clip.get('volume', 1))))
        if not all(math.isfinite(number) for number in (start, end, source_in, source_out, volume, speed)) or end <= start:
            raise ValueError('An audio clip has invalid timing.')
        gain_filter = volume_filter(clip, speed)
        index = len(filters) + 1
        command.extend(['-i', str(source)])
        tempo = []
        while speed > 2:
            tempo.append('atempo=2'); speed /= 2
        while speed < 0.5:
            tempo.append('atempo=0.5'); speed /= 0.5
        tempo.append(f'atempo={speed:.8f}')
        filters.append(f'[{index}:a]atrim=start={source_in:.8f}:end={source_out:.8f},asetpts=PTS-STARTPTS,'
                       + ','.join(tempo) + f',atrim=duration={end-start:.8f},asetpts=N/SR/TB,' + gain_filter + ','
                       + f'adelay={round(start*1000)}:all=1,asetpts=N/SR/TB[a{index}]')
    if not filters:
        return
    labels = ''.join(f'[a{index}]' for index in range(1, len(filters) + 1))
    filters.append(labels + f'amix=inputs={len(filters)}:normalize=0:dropout_transition=0[aout]')
    target = output.with_name('mixed-' + output.name)
    duration = probe_media(output)['duration']
    command.extend(['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[aout]', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '192k', '-t', str(duration), str(target)])
    if cancel.is_set():
        raise ValueError('Processing cancelled.')
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name != 'nt',
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    from .jobs import _processes
    _processes[identity] = process
    try:
        process.communicate(timeout=int(os.getenv('EDITOR_JOB_TIMEOUT_SECONDS', '1800')))
        if cancel.is_set():
            raise ValueError('Processing cancelled.')
        if process.returncode:
            raise ValueError('The audio mix failed. Check source timing and supported audio formats.')
        target.replace(output)
    finally:
        if process.poll() is None:
            stop_process(process); process.wait(timeout=10)
        target.unlink(missing_ok=True)


def media_path(reference):
    parsed = urlparse(str(reference))
    path = unquote(parsed.path)
    if path.startswith('/api/editor/assets/file/'):
        return store.get_blob(owner(), path.removeprefix('/api/editor/assets/file/'))
    if path.startswith('/api/uploads/'):
        return store.get_blob(owner(), 'uploads/' + path.removeprefix('/api/uploads/'))
    if path.startswith('/api/editor/projects/'):
        parts = path.split('/')
        if len(parts) < 7 or parts[5] != 'files':
            raise ValueError('Media does not belong to this workspace.')
        from .teams import project_owner
        return store.get_blob(project_owner(parts[4]), 'projects/' + parts[4] + '/' + '/'.join(parts[6:]))
    raise ValueError('Import media into the project before processing it on the backend.')


def run_operation(kind, payload, identity, cancel, progress):
    # Each job owns one direct scratch directory. Durable outputs are copied to
    # private Storage by the worker bridge before this directory is removed.
    processing_root = store.blob_path(owner(), 'processing').resolve()
    folder = store.blob_path(owner(), 'processing/' + identity).resolve()
    if folder.parent != processing_root:
        raise ValueError('Invalid processing job identifier.')
    try:
        return _run_operation(kind, payload, identity, cancel, progress)
    finally:
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


def _run_operation(kind, payload, identity, cancel, progress):
    from app.core.config import FFMPEG_PATH, FFPROBE_PATH
    folder = store.blob_path(owner(), 'processing/' + identity)
    folder.mkdir(parents=True, exist_ok=True)
    body = {'operation': kind, 'payload': copy.deepcopy(payload), 'folder': str(folder)}
    if kind == 'surface-map' and payload.get('options', {}).get('engine') == 'depth-gradient':
        from .surface import depth_gradient
        return depth_gradient(payload, identity)
    if kind == 'gemini':
        validate_sdk(body['payload'])
        if body['payload'].get('namespace') == 'files' and body['payload'].get('method') == 'upload':
            upload = body['payload'].get('params', {}).get('file')
            if not isinstance(upload, dict) or '__blob' not in upload:
                raise ValueError('Upload a browser file; server filesystem paths are not accepted.')
        body['credential'] = credential('gemini')
        if not body['credential']:
            raise ValueError('Add your Google Gemini key in Connections.')
    elif kind in ('surface-map', 'corridor-key'):
        repo = os.getenv('EDITOR_SURFACE_MAP_REPO' if kind == 'surface-map' else 'EDITOR_CORRIDOR_KEY_REPO', '')
        if not repo or not Path(repo).is_dir():
            raise ValueError('The backend operator must provision this processor and its model weights.')
        body['payload']['repoPath'] = repo
        body['payload']['projectPath'] = str(folder)
        for field in ('source', 'alpha'):
            item = body['payload'].get(field)
            if item and (not isinstance(item, dict) or not isinstance(item.get('base64'), str)):
                raise ValueError('Upload source media before processing it.')
    elif kind == 'export':
        project = body['payload'].get('project') or {}
        for media in project.get('mediaItems', []):
            source = media_path(media.get('url') or '')
            media['path'] = str(source)
            media['url'] = source.as_uri()
            media['sourceUrl'] = source.as_uri()
        settings = body['payload'].setdefault('settings', {})
        settings['filename'] = safe_relative(str(settings.get('filename', 'rayflow-export.mp4'))).split('/')[-1]
        if not project.get('timelineClips'):
            raise ValueError('Add clips to the timeline before exporting.')
    elif kind in ('audio-mastering', 'audio-remaster'):
        options = body['payload']
        for key in ('targetPath', 'referencePath'):
            if options.get(key):
                options[key] = str(media_path(options[key]))
        options['outputPath'] = str(folder / 'master.wav')
        if kind == 'audio-remaster':
            options['previewPath'] = str(folder / 'preview.wav')
        options['ffmpegPath'] = FFMPEG_PATH
        if not options.get('targetPath') or (kind == 'audio-remaster' and not options.get('referencePath')):
            raise ValueError('Source audio and the required reference must be uploaded first.')
        config = folder / 'config.json'
        config.write_text(json.dumps(options), encoding='utf-8')
    else:
        raise ValueError('This processor has not been configured for the hosted runtime.')
    if kind in ('audio-mastering', 'audio-remaster'):
        command = [sys.executable, str(RUNTIME / ('audio_mastering_worker.py' if kind == 'audio-mastering' else 'audio_remaster_worker.py')), str(config)]
    else:
        command = ['node', str(RUNTIME / 'worker.mjs')]
    environment = {**os.environ, 'IMAGEIO_FFMPEG_EXE': str(FFMPEG_PATH), 'FFPROBE_PATH': str(FFPROBE_PATH), 'PYTHON_PATH': sys.executable}
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', cwd=RUNTIME, env=environment,
                               start_new_session=os.name != 'nt',
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    from .jobs import _processes
    _processes[identity] = process
    process.stdin.write(json.dumps(body)); process.stdin.close()
    stderr_chunks = []
    def drain():
        for line in process.stderr:
            # Drain the pipe to prevent deadlock. Do not log credentials or commands.
            stderr_chunks.append(line[-200:])
            if len(stderr_chunks) > 10:
                stderr_chunks.pop(0)
    threading.Thread(target=drain, daemon=True).start()
    deadline = threading.Timer(int(os.getenv('EDITOR_JOB_TIMEOUT_SECONDS', '1800')), lambda: stop_process(process))
    deadline.start()
    result = None
    try:
        for line in process.stdout:
            if cancel.is_set():
                stop_process(process)
                raise ValueError('Processing cancelled.')
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if 'progress' in event:
                progress(float(event['progress']))
            if 'error' in event:
                raise ValueError(event['error'])
            if 'result' in event:
                result = event['result']
            elif event.get('ok'):
                result = event
        status = process.wait(timeout=20)
        if status or result is None:
            raise ValueError('The processing worker failed. Check its dependencies and source media.')
        if isinstance(result, dict) and result.get('outputPath'):
            output = Path(result['outputPath']).resolve()
            if folder.resolve() not in output.parents:
                raise ValueError('The worker returned an invalid output path.')
            if kind == 'export':
                mix_timeline_audio(output, payload.get('project') or {}, identity, cancel)
            relative = 'generated/' + identity + output.suffix
            store.put_blob(owner(), relative, output.read_bytes())
            result['url'] = '/api/editor/assets/file/' + relative
            result['outputPath'] = result['url']
            result.pop('previewPath', None)
            result.pop('logLines', None)
            result.pop('outputFolder', None)
            store.put('assets', identity, owner(), {'name': output.name, 'path': relative,
                      'type': 'audio' if kind.startswith('audio-') else 'image' if output.suffix.lower() in ('.png', '.jpg', '.webp') else 'video',
                      'size': output.stat().st_size, 'url': result['url'], 'job_id': identity})
        return result
    finally:
        deadline.cancel()
        if process.poll() is None:
            stop_process(process)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
