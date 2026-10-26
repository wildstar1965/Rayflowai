import type { TimelineClip } from '../types';

export function splitTimelineClip(clip: TimelineClip, at: number, newId: string): [TimelineClip, TimelineClip] | null {
  const speed = Math.max(.05, clip.speed || 1);
  const sourceIn = clip.sourceIn ?? 0;
  const sourceOut = clip.sourceOut ?? sourceIn + clip.duration;
  const offset = (at - clip.start) * speed;
  const sourceAt = sourceIn + offset;
  if (at - clip.start < .05 || clip.end - at < .05 || sourceAt - sourceIn < .05 || sourceOut - sourceAt < .05) return null;
  const first = { ...clip, end: at, duration: sourceAt - sourceIn, sourceIn, sourceOut: sourceAt, transitionOut: undefined };
  const second = { ...clip, id: newId, start: at, duration: sourceOut - sourceAt, sourceIn: sourceAt, sourceOut,
    // Keep the original interpolation segments, including their easing. Earlier
    // keys become negative rather than restarting the animation at the cut.
    keyframes: clip.keyframes?.map(key => ({ ...key, time: key.time - offset })) };
  if (clip.kenBurns?.enabled) {
    const { start, end } = clip.kenBurns;
    const p = offset / (sourceOut - sourceIn);
    const middle = { x: start.x + (end.x - start.x) * p, y: start.y + (end.y - start.y) * p,
      scale: start.scale + (end.scale - start.scale) * p };
    first.kenBurns = { ...clip.kenBurns, end: middle };
    second.kenBurns = { ...clip.kenBurns, start: middle };
  }
  return [first, second];
}
