import type { EditingPlan } from '../types';

export function isEditingText(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (!!target.closest('input, textarea, select, [role="textbox"]') || target.isContentEditable);
}

export function deleteCaptions(plan: EditingPlan, ids: string[]): EditingPlan {
  const selected = new Set(ids);
  const removed = (plan.subtitles || []).filter(caption => selected.has(caption.id));
  if (!removed.length) return plan;
  return { ...plan, subtitles: plan.subtitles?.filter(caption => !selected.has(caption.id)),
    transcript: [...(plan.transcript || []).filter(caption => !selected.has(caption.id)), ...removed] };
}
