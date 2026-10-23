"""Conservative timeline interchange. Originals and production documents are retained."""
import copy
import math
import uuid
from urllib.parse import unquote, urlparse


def number(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('The sequence contains invalid timing.')
    return float(value)


def transfer(sequence, destination, project_id):
    source = copy.deepcopy(sequence['document'])
    if destination == sequence['kind']:
        return source
    reasons = []
    if sequence['kind'] == 'rayflow' and destination == 'editor':
        plan = source.get('plan', {})
        for field in ('subtitles', 'visual_inserts', 'sound_cues', 'cinematic_texts'):
            if plan.get(field):
                reasons.append(field.replace('_', ' '))
        for field in ('title', 'head_transition', 'tail_transition'):
            if plan.get(field, {}).get('enabled'):
                reasons.append(field.replace('_', ' '))
        if any(row.get('enabled', True) and row.get('type') not in ('none', 'cut') for row in plan.get('transitions', [])):
            reasons.append('transitions')
        if plan.get('color_strength', 1) != 0:
            reasons.append('Rayflow color grade (set strength to zero first)')
        if plan.get('aspect_ratio', '16:9') != '16:9' or plan.get('fit_mode', 'fill') != 'fill':
            reasons.append('canvas aspect ratio or fit mode')
        media, clips = [], []
        assets = {asset.get('filename'): asset for asset in source.get('images', [])}
        for index, clip in enumerate(plan.get('clips', [])):
            if clip.get('motion', 'static') != 'static' or clip.get('transition', 'none') not in ('none', 'cut'):
                reasons.append('clip motion or transitions')
            start, duration = number(clip['start_time']), number(clip['duration'])
            source_in = number(clip.get('source_start', 0))
            if start < 0 or duration <= 0 or source_in < 0:
                reasons.append('invalid clip timing')
            media_id = 'transfer-media-' + str(index)
            reference = clip['image_url']
            if not reference.startswith('/api/'):
                reference = assets.get(reference, {}).get('url', '')
            if not reference.startswith(('/api/uploads/', '/api/editor/assets/file/', '/api/editor/projects/')):
                reasons.append('media requiring import or relinking')
            media.append({'id': media_id, 'name': clip.get('label') or 'Transferred clip',
                          'type': clip.get('media_type', 'image'), 'path': reference, 'source': 'upload'})
            clips.append({'id': str(uuid.uuid4()), 'mediaId': media_id, 'trackId': 'transfer-video',
                          'start': start, 'end': start + duration, 'duration': duration, 'speed': 1,
                          'sourceIn': source_in, 'sourceOut': source_in + duration, 'volume': clip.get('volume', 1), 'effect': None})
        audio = source.get('audio')
        if audio:
            duration = number(plan.get('duration_seconds', 0))
            media.append({'id': 'transfer-audio', 'name': audio.get('original_name', 'Music'), 'type': 'audio',
                          'path': audio['url'], 'source': 'upload'})
            clips.append({'id': str(uuid.uuid4()), 'mediaId': 'transfer-audio', 'trackId': 'transfer-audio',
                          'start': 0, 'end': duration, 'duration': duration, 'speed': 1, 'sourceIn': 0,
                          'sourceOut': duration, 'volume': plan.get('music_volume', 1), 'effect': None})
        output = {'version': 1, 'name': sequence['name'], 'mediaItems': media, 'timelineClips': clips,
                  'timelineTracks': [{'id': 'transfer-' + kind, 'type': kind, 'name': kind.title(),
                                      'isLocked': False, 'isMuted': False} for kind in ('video', 'audio')]}
    elif sequence['kind'] == 'editor' and destination == 'rayflow':
        media = {row['id']: row for row in source.get('mediaItems', [])}
        tracks = {row['id']: row for row in source.get('timelineTracks', [])}
        clips, images, audio = [], [], None
        end = 0
        for clip in sorted(source.get('timelineClips', []), key=lambda row: row['start']):
            item = media.get(clip.get('mediaId'), {})
            track = tracks.get(clip.get('trackId'), {})
            if track.get('isMuted') or track.get('isSolo'):
                reasons.append('muted or solo tracks')
            for field in ('effect', 'effects', 'transitionOut', 'textConfig', 'subtitleSegment', 'keyframes', 'chromaKey'):
                if clip.get(field):
                    reasons.append(field)
            if clip.get('filters'):
                neutral = {'brightness': 100, 'contrast': 100, 'saturate': 100, 'hueRotate': 0, 'grain': 0,
                           'halation': 0, 'bloom': 0, 'vignette': 0, 'lut': 'none', 'lutIntensity': 100,
                           'customLut': None, 'customLutName': None, 'colorWheels': None}
                if any(value != neutral.get(key) for key, value in clip['filters'].items()):
                    reasons.append('color filters')
            if clip.get('transform') not in (None, {'scale': 1, 'opacity': 1, 'position': {'x': 50, 'y': 50}}):
                reasons.append('transform')
            if clip.get('kenBurns', {}).get('enabled') or clip.get('speed', 1) != 1 or clip.get('blendMode', 'normal') != 'normal':
                reasons.append('animation, speed or blending')
            reference = item.get('url') or item.get('path') or ''
            if not reference.startswith('/api/'):
                if urlparse(reference).scheme or not reference:
                    reasons.append('media requiring import or relinking')
                else:
                    reference = f'/api/editor/projects/{project_id}/files/{reference}'
            start, stop = number(clip['start']), number(clip['end'])
            if stop <= start or start < 0:
                reasons.append('invalid clip timing')
            descriptor = {'filename': reference,
                          'original_name': item.get('name', 'Transferred media'), 'url': reference, 'size': 0}
            if item.get('type') == 'audio':
                if audio or start != 0 or clip.get('sourceIn', 0) != 0 or clip.get('volume', 1) != 1:
                    reasons.append('multiple, trimmed or mixed audio tracks')
                audio = descriptor
                continue
            if item.get('type') not in ('image', 'video'):
                reasons.append('non-media clips')
            if abs(start - end) > .001:
                reasons.append('overlapping clips or timeline gaps')
            end = stop
            images.append({**descriptor, 'media_type': item.get('type', 'image')})
            clips.append({'id': str(uuid.uuid4()), 'image_url': reference, 'start_time': start, 'duration': stop - start,
                          'source_start': clip.get('sourceIn', 0), 'media_type': item.get('type', 'image'),
                          'motion': 'static', 'transition': 'none', 'label': item.get('name', ''), 'volume': clip.get('volume', 1)})
        if audio:
            reasons.append('external timeline audio (use shared assets to add music in Studio)')
        output = {'projectName': sequence['name'], 'images': images, 'audio': audio, 'audioAnalysis': None,
                  'plan': {'clips': clips, 'duration_seconds': end, 'aspect_ratio': '16:9', 'fit_mode': 'fill',
                           'style': 'minimal', 'color_strength': 0, 'beat_sync': False, 'cut_pacing': 'balanced',
                           'motion': 'static', 'title': {'enabled': False, 'text': '', 'gradient': []}, 'transitions': []}}
    else:
        raise ValueError('Unsupported sequence conversion.')
    if reasons:
        raise ValueError('Transfer cannot preserve: ' + ', '.join(sorted(set(reasons))) + '. The original sequence is unchanged. Export a rendered movie to transfer its finished appearance.')
    output['rayflowTransfer'] = {'sourceSequence': sequence['id'], 'sourceKind': sequence['kind'], 'originalDocument': source}
    return output
