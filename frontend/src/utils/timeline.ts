import { ClipConfig, TransitionConfig, EditingPlan, UploadedImage } from '../types';

export function uploadedClip(item: UploadedImage, start: number): ClipConfig {
  const video = item.media_type === 'video';
  const duration = video ? item.duration : 2.5;
  if (duration === undefined || !Number.isFinite(duration) || duration <= 0) {
    throw new Error(`Cannot read source duration: ${item.original_name}`);
  }
  return { id: crypto.randomUUID(), image_url: item.url, start_time: start, duration,
    source_start: 0, source_duration: video ? duration : undefined,
    media_type: video ? 'video' : 'image', motion: video ? 'static' : 'zoom_in', transition: 'none' };
}

/**
 * Reorders clips using stable clip IDs and explicit drop positioning ('before' | 'after').
 * Handles moving any clip forward, backward, first to last, last to first,
 * and maintains images alongside video clips.
 */
export function reorderClips(
  clips: ClipConfig[],
  sourceClipId: string,
  targetClipId: string,
  position: 'before' | 'after' = 'before'
): ClipConfig[] {
  if (!clips || clips.length <= 1) return clips;
  if (sourceClipId === targetClipId) return clips;

  const sourceClip = clips.find(c => c.id === sourceClipId);
  const targetIndex = clips.findIndex(c => c.id === targetClipId);

  if (!sourceClip || targetIndex === -1) return clips;

  // Filter out the source clip without mutating original
  const remaining = clips.filter(c => c.id !== sourceClipId);
  const newTargetIndex = remaining.findIndex(c => c.id === targetClipId);

  if (newTargetIndex === -1) return clips;

  const insertIndex = position === 'after' ? newTargetIndex + 1 : newTargetIndex;
  const result = [...remaining];
  result.splice(insertIndex, 0, sourceClip);

  return result;
}

/**
 * Validates transition endpoints against the current clip sequence.
 * Preserves unaffected transitions, clamps durations when clips are trimmed,
 * purges invalid or non-adjacent transitions, and creates clean boundary transitions for new pairs.
 */
export function reconcileTransitions(
  clips: ClipConfig[],
  existingTransitions: TransitionConfig[] = []
): TransitionConfig[] {
  if (!clips || clips.length < 2) return [];

  const result: TransitionConfig[] = [];
  const transMap = new Map<string, TransitionConfig>();

  for (const t of existingTransitions) {
    if (t && t.from_clip_id && t.to_clip_id) {
      transMap.set(`${t.from_clip_id}->${t.to_clip_id}`, t);
    }
  }

  for (let i = 0; i < clips.length - 1; i++) {
    const c1 = clips[i];
    const c2 = clips[i + 1];
    const key = `${c1.id}->${c2.id}`;
    const matched = transMap.get(key);

    const rawAllowed = Math.min(c1.duration, c2.duration) - 0.1;
    const maxAllowedDur = Math.max(0, Math.round(rawAllowed * 1e9) / 1e9);

    if (matched) {
      // Preserve existing transition, clamping duration safely to fit adjacent clips
      result.push({
        ...matched,
        duration: Math.max(0, Math.min(matched.duration, maxAllowedDur, 2.0)),
        enabled: matched.enabled && matched.type !== 'none' && maxAllowedDur > 0
      });
    } else {
      // Rebuild clean transition for newly adjacent boundary
      const defaultType = c1.transition && c1.transition !== 'none' ? c1.transition : 'none';
      result.push({
        id: `trans-${c1.id}-${c2.id}`,
        from_clip_id: c1.id,
        to_clip_id: c2.id,
        type: defaultType as any,
        duration: Math.min(0.5, maxAllowedDur),
        enabled: defaultType !== 'none' && maxAllowedDur > 0
      });
    }
  }

  return result;
}

/**
 * Recalculates start times, total duration, and synchronized transitions.
 */
export function recalculateTimeline(
  clips: ClipConfig[],
  existingTransitions: TransitionConfig[],
  plan: EditingPlan
): EditingPlan {
  let accTime = 0.0;
  const syncedClips: ClipConfig[] = clips.map(c => {
    const start = accTime;
    const dur = c.duration;
    accTime += dur;
    return {
      ...c,
      start_time: start,
      duration: dur
    };
  });

  const totalDuration = accTime;
  const syncedTransitions = reconcileTransitions(syncedClips, existingTransitions);

  return {
    ...plan,
    duration_seconds: totalDuration,
    clips: syncedClips,
    transitions: syncedTransitions,
    ...retimeAttached(plan, syncedClips, totalDuration)
  };
}

function retimeAttached(plan: EditingPlan, clips: ClipConfig[], duration: number) {
  const result: Partial<EditingPlan> = {};
  for (const key of ['subtitles', 'visual_inserts', 'sound_cues', 'cinematic_texts'] as const) {
    const items = (plan[key] || []).flatMap(item => {
      if (!item.source_clip_id) return item.start_time < duration ? [item] : [];
      const previous = plan.clips.find(c => c.id === item.source_clip_id);
      const clip = clips.find(c => c.id === item.source_clip_id);
      if (!clip || !previous) return [];
      const delta = clip.start_time - previous.start_time - ((clip.source_start || 0) - (previous.source_start || 0));
      const start = item.start_time + delta;
      const end = ('end_time' in item ? item.end_time : item.start_time + ('duration' in item ? item.duration : .1)) + delta;
      if (start >= clip.start_time + clip.duration || end <= clip.start_time) return [];
      const updated = { ...item, start_time: Math.max(clip.start_time, start) };
      if ('end_time' in updated) {
        updated.end_time = Math.min(end, clip.start_time + clip.duration);
        updated.words = updated.words?.map(w => ({ ...w, start: Math.max(updated.start_time, w.start + delta), end: Math.min(updated.end_time, w.end + delta) })).filter(w => w.end > w.start);
      } else if ('duration' in updated) updated.duration = Math.min(end, clip.start_time + clip.duration) - updated.start_time;
      if ('behind_subject' in updated && clip.source_start !== previous.source_start) updated.behind_subject = false;
      return [updated];
    });
    Object.assign(result, { [key]: items });
  }
  return result;
}
