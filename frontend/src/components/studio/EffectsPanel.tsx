import React from 'react';
import { EditingPlan, TransitionType, TransitionConfig, GlobalTransitionConfig, UploadedImage } from '../../types';
import { Sparkles, ArrowRight } from 'lucide-react';

interface EffectsPanelProps {
  plan: EditingPlan;
  images: UploadedImage[];
  selectedTransitionId: string | null;
  onUpdatePlan: (updatedPlan: EditingPlan) => void;
  onSelectTransition: (transitionId: string | null) => void;
}

export const EffectsPanel: React.FC<EffectsPanelProps> = ({
  plan,
  selectedTransitionId,
  onUpdatePlan,
  onSelectTransition
}) => {
  const clips = plan.clips;
  const clipCount = clips.length;

  // Ensure transitions array exists
  const transitions = plan.transitions || [];

  // Helper to get or create transition for adjacent clips
  const getTransitionForBoundary = (fromClipId: string, toClipId: string): TransitionConfig => {
    const existing = transitions.find(t => t.from_clip_id === fromClipId && t.to_clip_id === toClipId);
    if (existing) return existing;
    const fromClip = clips.find(c => c.id === fromClipId);
    return {
      id: `boundary-${fromClipId}-${toClipId}`,
      from_clip_id: fromClipId,
      to_clip_id: toClipId,
      type: (fromClip?.transition as TransitionType) || 'none',
      duration: 0.5,
      enabled: Boolean(fromClip?.transition && fromClip.transition !== 'none')
    };
  };

  // Update a single boundary transition
  const handleUpdateBoundaryTransition = (
    fromClipId: string,
    toClipId: string,
    updates: Partial<TransitionConfig>
  ) => {
    const fromClip = clips.find(c => c.id === fromClipId);
    const toClip = clips.find(c => c.id === toClipId);
    if (!fromClip || !toClip) return;

    // Max duration allowed
    const maxDur = Math.max(0.1, Math.min(fromClip.duration, toClip.duration) - 0.1);
    const existing = transitions.find(t => t.from_clip_id === fromClipId && t.to_clip_id === toClipId);
    let dur = updates.duration !== undefined ? updates.duration : existing?.duration ?? 0.5;
    dur = Math.max(0.1, Math.min(dur, maxDur, 2.0));

    const existingIdx = transitions.findIndex(t => t.from_clip_id === fromClipId && t.to_clip_id === toClipId);
    let updatedTransitions = [...transitions];

    if (existingIdx >= 0) {
      updatedTransitions[existingIdx] = {
        ...updatedTransitions[existingIdx],
        ...updates,
        duration: dur
      };
    } else {
      updatedTransitions.push({
        id: `trans-${fromClipId}-${toClipId}`,
        from_clip_id: fromClipId,
        to_clip_id: toClipId,
        type: updates.type || 'crossfade',
        duration: dur,
        enabled: updates.enabled !== undefined ? updates.enabled : true
      });
    }

    // Also update clip.transition on fromClip for backwards compatibility
    const updatedClips = clips.map(c => {
      if (c.id === fromClipId && updates.type) {
        return { ...c, transition: updates.type };
      }
      return c;
    });

    onUpdatePlan({
      ...plan,
      clips: updatedClips,
      transitions: updatedTransitions
    });
  };

  // Apply batch crossfade to all boundaries
  const handleApplyAllCrossfade = (duration: number = 0.5) => {
    if (clipCount < 2) return;
    const newTransitions: TransitionConfig[] = [];
    const updatedClips = clips.map((c, i) => {
      if (i < clipCount - 1) {
        const nextC = clips[i + 1];
        const maxD = Math.max(0.1, Math.min(c.duration, nextC.duration) - 0.1);
        const appliedDur = Math.min(duration, maxD);
        newTransitions.push({
          id: `trans-${i + 1}`,
          from_clip_id: c.id,
          to_clip_id: nextC.id,
          type: 'crossfade',
          duration: appliedDur,
          enabled: true
        });
        return { ...c, transition: 'crossfade' as TransitionType };
      }
      return c;
    });

    onUpdatePlan({
      ...plan,
      clips: updatedClips,
      transitions: newTransitions
    });
  };

  // Remove all boundary transitions (direct cuts)
  const handleClearAllTransitions = () => {
    const updatedTransitions = transitions.map(t => ({ ...t, type: 'none' as TransitionType, enabled: false }));
    const updatedClips = clips.map(c => ({ ...c, transition: 'none' as TransitionType }));
    onUpdatePlan({
      ...plan,
      clips: updatedClips,
      transitions: updatedTransitions
    });
  };

  // Global Head Transition Handler
  const handleUpdateHeadTransition = (updates: Partial<GlobalTransitionConfig>) => {
    const current = plan.head_transition || { enabled: false, type: 'fade_in', duration: 0.5 };
    onUpdatePlan({
      ...plan,
      head_transition: { ...current, ...updates }
    });
  };

  // Global Tail Transition Handler
  const handleUpdateTailTransition = (updates: Partial<GlobalTransitionConfig>) => {
    const current = plan.tail_transition || { enabled: false, type: 'fade_out', duration: 0.5 };
    onUpdatePlan({
      ...plan,
      tail_transition: { ...current, ...updates }
    });
  };

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="flex items-center justify-between pb-1 border-b border-studio-border">
        <div>
          <h4 className="text-xs font-semibold text-studio-text flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-studio-text" />
            <span>Shape the cut</span>
          </h4>
          <p className="text-[11px] text-studio-muted mt-0.5">
            Guide each cut in Rayflow, from the opening frame to the final fade.
          </p>
        </div>
      </div>

      {/* Quick Batch Actions */}
      <div className="p-3 bg-studio-raised rounded-xl border border-studio-border space-y-2">
        <span className="text-[11px] font-semibold text-studio-text block uppercase tracking-wider font-mono">
          Edit the rhythm
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleApplyAllCrossfade(0.5)}
            className="flex-1 py-1.5 px-2.5 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent-hover transition-colors shadow-2xs text-center"
          >
            Crossfade all (0.5s)
          </button>
          <button
            onClick={handleClearAllTransitions}
            className="py-1.5 px-2.5 rounded-lg bg-studio-panel text-studio-text hover:text-danger border border-studio-border hover:border-studio-border text-xs font-medium transition-colors shadow-2xs"
            title="Reset all transitions to direct cuts"
          >
            Use direct cuts
          </button>
        </div>
      </div>

      {/* GLOBAL HEAD / TAIL SECTION */}
      <div className="space-y-3">
        <span className="text-[11px] font-semibold text-studio-text block uppercase tracking-wider font-mono">
          Opening and closing
        </span>

        {/* Start of Reel (Head) */}
        <div className="p-3 rounded-xl bg-studio-panel border border-studio-border shadow-2xs space-y-2.5">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-studio-text block">
                Opening fade
              </span>
              <span className="text-[10px] text-studio-muted">
                Fade your reel in from a solid color
              </span>
            </div>
            <input
              type="checkbox"
              checked={Boolean(plan.head_transition?.enabled)}
              onChange={e => handleUpdateHeadTransition({ enabled: e.target.checked })}
              className="w-4 h-4 accent-accent rounded cursor-pointer"
            />
          </div>

          {plan.head_transition?.enabled && (
            <div className="pt-2 border-t border-studio-line space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-studio-muted">Type</span>
                <select
                  value={plan.head_transition.type || 'fade_in'}
                  onChange={e => handleUpdateHeadTransition({ type: e.target.value as any })}
                  className="text-xs bg-studio-raised border border-studio-border rounded px-2 py-1 font-medium text-studio-text outline-none"
                >
                  <option value="fade_in">Fade in from Black</option>
                  <option value="dip_black">Dip to Black</option>
                  <option value="dip_white">Dip to White</option>
                </select>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-studio-muted">Duration</span>
                  <span className="font-mono font-semibold text-studio-text">
                    {(plan.head_transition.duration || 0.5).toFixed(1)}s
                  </span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.0"
                  step="0.1"
                  value={plan.head_transition.duration || 0.5}
                  onChange={e => handleUpdateHeadTransition({ duration: parseFloat(e.target.value) })}
                  className="w-full accent-accent h-1.5 bg-studio-line rounded-lg cursor-pointer"
                />
              </div>
            </div>
          )}
        </div>

        {/* End of Reel (Tail) */}
        <div className="p-3 rounded-xl bg-studio-panel border border-studio-border shadow-2xs space-y-2.5">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-studio-text block">
                Closing fade
              </span>
              <span className="text-[10px] text-studio-muted">
                Fade your reel out to a solid color
              </span>
            </div>
            <input
              type="checkbox"
              checked={Boolean(plan.tail_transition?.enabled)}
              onChange={e => handleUpdateTailTransition({ enabled: e.target.checked })}
              className="w-4 h-4 accent-accent rounded cursor-pointer"
            />
          </div>

          {plan.tail_transition?.enabled && (
            <div className="pt-2 border-t border-studio-line space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-studio-muted">Type</span>
                <select
                  value={plan.tail_transition.type || 'fade_out'}
                  onChange={e => handleUpdateTailTransition({ type: e.target.value as any })}
                  className="text-xs bg-studio-raised border border-studio-border rounded px-2 py-1 font-medium text-studio-text outline-none"
                >
                  <option value="fade_out">Fade out to Black</option>
                  <option value="dip_black">Dip to Black</option>
                  <option value="dip_white">Dip to White</option>
                </select>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-studio-muted">Duration</span>
                  <span className="font-mono font-semibold text-studio-text">
                    {(plan.tail_transition.duration || 0.5).toFixed(1)}s
                  </span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.0"
                  step="0.1"
                  value={plan.tail_transition.duration || 0.5}
                  onChange={e => handleUpdateTailTransition({ duration: parseFloat(e.target.value) })}
                  className="w-full accent-accent h-1.5 bg-studio-line rounded-lg cursor-pointer"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* CLIP BOUNDARIES LIST */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-studio-text uppercase tracking-wider font-mono">
            Between clips ({Math.max(0, clipCount - 1)})
          </span>
          <span className="text-[10px] text-studio-muted">
            {clipCount < 2 ? 'Add two clips to begin' : 'Set each cut between clips'}
          </span>
        </div>

        {clipCount < 2 ? (
          <div className="text-center py-6 px-4 text-xs text-studio-muted border border-studio-border rounded-xl bg-studio-panel">
            Add at least two photos or videos to shape the transitions in your Rayflow reel.
          </div>
        ) : (
          <div className="space-y-2.5">
            {clips.slice(0, clipCount - 1).map((clipFrom, i) => {
              const clipTo = clips[i + 1];
              const trans = getTransitionForBoundary(clipFrom.id, clipTo.id);
              const isSelected = selectedTransitionId === trans.id;
              const maxDur = Math.max(0.1, Math.min(clipFrom.duration, clipTo.duration) - 0.1);

              return (
                <div
                  key={trans.id}
                  onClick={() => onSelectTransition(trans.id)}
                  className={`p-3 rounded-xl bg-studio-panel border transition-all shadow-2xs space-y-2.5 ${
                    isSelected ? 'border-accent ring-2 ring-accent' : 'border-studio-border hover:border-studio-border'
                  }`}
                >
                  {/* Boundary Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-medium text-studio-text">
                      <span className="px-1.5 py-0.5 rounded bg-studio-hover font-mono text-[11px]">
                        #{i + 1}
                      </span>
                      <ArrowRight className="w-3 h-3 text-studio-quiet" />
                      <span className="px-1.5 py-0.5 rounded bg-studio-hover font-mono text-[11px]">
                        #{i + 2}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <label className="text-[11px] text-studio-muted flex items-center gap-1 cursor-pointer">
                        <span>Active</span>
                        <input
                          type="checkbox"
                          checked={trans.enabled && trans.type !== 'none'}
                          onChange={e => {
                            handleUpdateBoundaryTransition(clipFrom.id, clipTo.id, {
                              enabled: e.target.checked,
                              type: e.target.checked ? (trans.type === 'none' ? 'crossfade' : trans.type) : 'none'
                            });
                          }}
                          className="w-3.5 h-3.5 accent-accent rounded cursor-pointer"
                        />
                      </label>
                    </div>
                  </div>

                  {/* Controls */}
                  <div className="grid grid-cols-2 gap-2 pt-1 border-t border-studio-line">
                    <div>
                      <label className="text-[10px] text-studio-muted block mb-0.5">Transition style</label>
                      <select
                        value={trans.enabled ? trans.type : 'none'}
                        onChange={e => {
                          const val = e.target.value as TransitionType;
                          handleUpdateBoundaryTransition(clipFrom.id, clipTo.id, {
                            type: val,
                            enabled: val !== 'none'
                          });
                        }}
                        className="w-full text-xs bg-studio-raised border border-studio-border rounded px-2 py-1 text-studio-text font-medium outline-none"
                      >
                        <option value="none">None (Direct Cut)</option>
                        <option value="crossfade">Crossfade (Dissolve)</option>
                        <option value="dip_black">Dip to Black</option>
                        <option value="dip_white">Dip to White</option>
                        <option value="fade_in">Fade In</option>
                        <option value="fade_out">Fade Out</option>
                      </select>
                    </div>

                    <div>
                      <div className="flex justify-between items-center mb-0.5">
                        <label className="text-[10px] text-studio-muted">Duration</label>
                        <span className="text-[10px] font-mono font-semibold text-studio-text">
                          {trans.duration.toFixed(1)}s
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0.1"
                        max={Math.min(2.0, maxDur)}
                        step="0.1"
                        disabled={!trans.enabled || trans.type === 'none'}
                        value={trans.duration}
                        onChange={e => {
                          handleUpdateBoundaryTransition(clipFrom.id, clipTo.id, {
                            duration: parseFloat(e.target.value)
                          });
                        }}
                        className="w-full accent-accent h-1.5 bg-studio-line rounded-lg cursor-pointer disabled:opacity-40"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
