"""Translate timeline volume keyframes to FFmpeg's frame-evaluated gain curve."""
import math


def volume_filter(clip, speed):
    def number(value):
        try:
            result = float(value)
        except (ValueError, TypeError):
            raise ValueError('An audio volume keyframe is invalid.') from None
        if not math.isfinite(result):
            raise ValueError('An audio volume keyframe is invalid.')
        return result

    frames = [frame for frame in clip.get('keyframes', []) if frame.get('property') == 'volume']
    if not frames:
        return f'volume={max(0, min(1, number(clip.get("volume", 1)))):.8f}'
    if len(frames) > 128:
        raise ValueError('Reduce this clip to at most 128 volume keyframes before exporting.')
    frames = sorted(frames, key=lambda frame: number(frame.get('time')))
    points = []
    for frame in frames:
        moment, gain = number(frame.get('time')), number(frame.get('value'))
        if moment < 0 or (points and moment == points[-1][0]):
            raise ValueError('Audio volume keyframe times must be distinct and nonnegative.')
        easing = frame.get('easing', 'linear')
        if easing not in ('linear', 'ease-in', 'ease-out', 'ease-in-out'):
            raise ValueError('This audio volume easing is not supported.')
        points.append((moment, gain, easing))
    # Preview evaluates keyframes in source-relative time, excluding sourceIn.
    clock = f'(if(isnan(t),0,t)*{speed:.8f})'
    expression = f'{points[-1][1]:.8f}'
    for left, right in reversed(list(zip(points, points[1:]))):
        start, gain, _ = left
        end, next_gain, easing = right
        progress = f'(({clock}-{start:.8f})/{end-start:.8f})'
        if easing == 'ease-in':
            curve = f'pow({progress},2)'
        elif easing == 'ease-out':
            curve = f'({progress}*(2-{progress}))'
        elif easing == 'ease-in-out':
            curve = f'if(lt({progress},0.5),2*pow({progress},2),-1+(4-2*{progress})*{progress})'
        else:
            curve = progress
        segment = f'({gain:.8f}+({next_gain-gain:.8f})*{curve})'
        expression = f'if(lt({clock},{end:.8f}),{segment},{expression})'
    expression = f'if(lte({clock},{points[0][0]:.8f}),{points[0][1]:.8f},{expression})'
    # Match HTMLMediaElement.volume's [0,1] range. Only validated numbers and
    # fixed operators reach the filter expression, never client-supplied code.
    return f"volume='clip({expression},0,1)':eval=frame"
