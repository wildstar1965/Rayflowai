import type { EditingPlan } from '../types';

// Keep this grid in step with backend/app/services/frame_timing.py.
export const PREVIEW_FPS = 30;
export const frameAt = (seconds: number) => Math.floor(seconds * PREVIEW_FPS + 0.5 + 1e-9);

export function previewTimeline(plan: EditingPlan) {
  let elapsed = 0;
  let boundary = 0;
  return plan.clips.map(clip => {
    elapsed += clip.duration;
    const end = frameAt(elapsed);
    const start = boundary;
    boundary = end;
    return { ...clip, start_time: start / PREVIEW_FPS, duration: (end - start) / PREVIEW_FPS };
  });
}

export function transitionAt(plan: EditingPlan, clips: EditingPlan['clips'], index: number) {
  const from = clips[index], to = clips[index + 1];
  if (!from || !to) return null;
  const explicit = plan.transitions?.find(t => t.from_clip_id === from.id && t.to_clip_id === to.id);
  const type = explicit ? (explicit.enabled ? explicit.type : 'none') : from.transition;
  if (!type || type === 'none' || type === 'cut') return null;
  const maxFrames = Math.max(0, Math.min(frameAt(from.duration), frameAt(to.duration)) - 1);
  const frames = Math.min(maxFrames, frameAt(Math.max(0, Math.min(explicit?.duration ?? .5, from.duration - .1, to.duration - .1, 2))));
  return frames > 0 ? { type, duration: frames / PREVIEW_FPS } : null;
}
