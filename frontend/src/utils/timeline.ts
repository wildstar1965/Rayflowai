import { ClipConfig, TransitionConfig, EditingPlan } from '../types';

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
    const maxAllowedDur = Math.max(0.1, Math.round(rawAllowed * 100) / 100);

    if (matched) {
      // Preserve existing transition, clamping duration safely to fit adjacent clips
      result.push({
        ...matched,
        duration: Math.max(0.1, Math.min(matched.duration, maxAllowedDur, 2.0)),
        enabled: matched.enabled && matched.type !== 'none'
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
        enabled: defaultType !== 'none'
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
    const start = Math.round(accTime * 100) / 100;
    const dur = Math.max(0.5, Math.round(c.duration * 100) / 100);
    accTime += dur;
    return {
      ...c,
      start_time: start,
      duration: dur
    };
  });

  const totalDuration = Math.round(accTime * 100) / 100;
  const syncedTransitions = reconcileTransitions(syncedClips, existingTransitions);

  return {
    ...plan,
    duration_seconds: totalDuration,
    clips: syncedClips,
    transitions: syncedTransitions
  };
}
