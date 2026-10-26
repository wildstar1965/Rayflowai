import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import {
  EditingPlan,
  ClipConfig,
  AudioAnalysisResult,
  UploadedAudio
} from '../../types';
import { getMediaUrl } from '../../services/api';
import { reorderClips, recalculateTimeline } from '../../utils/timeline';
import {
  Plus,
  Minus,
  Trash2,
  ZoomIn,
  ZoomOut
} from 'lucide-react';

interface InteractiveTimelineProps {
  plan: EditingPlan;
  audio: UploadedAudio | null;
  audioAnalysis: AudioAnalysisResult | null;
  currentTime: number;
  isPlaying: boolean;
  selectedClipId: string | null;
  onSelectClip: (clipId: string | null) => void;
  selectedCaptionIds?: string[];
  onSelectCaption?: (id: string, multiple?: boolean) => void;
  audioSelected?: boolean;
  onSelectAudio?: () => void;
  onSeek: (time: number) => void;
  onScrubCommit?: (before: number, after: number) => void;
  onUpdatePlan: (updatedPlan: EditingPlan, recordHistory?: boolean) => void;
  onOpenEffectsForBoundary?: (fromClipId: string, toClipId: string) => void;
}

interface TrimmingActiveState {
  clipId: string;
  edge: 'left' | 'right';
  startX: number;
  initialDuration: number;
  initialStartTime: number;
  initialSourceStart: number;
  currentDuration: number;
}

export const InteractiveTimeline: React.FC<InteractiveTimelineProps> = ({
  plan,
  audio,
  audioAnalysis,
  currentTime,
  selectedClipId,
  onSelectClip,
  selectedCaptionIds = [],
  onSelectCaption,
  audioSelected = false,
  onSelectAudio,
  onSeek,
  onScrubCommit,
  onUpdatePlan,
  onOpenEffectsForBoundary
}) => {
  // Zoom state: 0.75x to 3.0x
  const [zoomLevel, setZoomLevel] = useState<number>(1.0);

  // Trimming interaction state
  const [trimmingState, setTrimmingState] = useState<TrimmingActiveState | null>(null);
  const pendingTrimPlanRef = useRef<EditingPlan | null>(null);

  // Drag-and-drop reordering state using stable clip IDs
  const [draggedClipId, setDraggedClipId] = useState<string | null>(null);
  const [dragTarget, setDragTarget] = useState<{ clipId: string; position: 'before' | 'after' } | null>(null);

  // Audio waveform peaks cache
  const [waveformPeaks, setWaveformPeaks] = useState<number[] | null>(null);
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Container refs for scroll sync
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const scrubRef = useRef<{ pointerId: number; grabOffset: number; initialTime: number; lastTime: number } | null>(null);
  const seekFrameRef = useRef<number | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const onSeekRef = useRef(onSeek);
  useLayoutEffect(() => { onSeekRef.current = onSeek; }, [onSeek]);
  const timelineOrigin = 33; // Padding + track label + track border.
  const [isScrubbing, setIsScrubbing] = useState(false);
  const overlayDrag = useRef<{key:'visual_inserts'|'subtitles'|'sound_cues';id:string;edge:'move'|'left'|'right';x:number;plan:EditingPlan;last:EditingPlan}|null>(null);
  const startOverlayDrag = (event:React.PointerEvent<HTMLElement>, key:'visual_inserts'|'subtitles'|'sound_cues',id:string,edge:'move'|'left'|'right'='move') => {
    if(event.button!==0)return;
    event.preventDefault();event.stopPropagation();event.currentTarget.setPointerCapture(event.pointerId);
    if (key === 'subtitles') {
      event.currentTarget.focus();
      onSelectCaption?.(id, event.shiftKey || event.ctrlKey || event.metaKey);
    } else onSelectClip(null);
    overlayDrag.current={key,id,edge,x:event.clientX,plan,last:plan};
  };
  const moveOverlayDrag = (event:React.PointerEvent<HTMLElement>) => {
    const drag=overlayDrag.current;if(!drag)return;event.preventDefault();event.stopPropagation();
    if (drag.last === drag.plan && Math.abs(event.clientX - drag.x) < 3) return;
    const delta=(event.clientX-drag.x)/pxPerSec;
    const items=drag.plan[drag.key]?.map(item=>{
      if(item.id!==drag.id)return item;
      const end='end_time' in item?item.end_time:item.start_time+('duration' in item?item.duration:.1);
      const duration=end-item.start_time;
      const start=drag.edge==='right'?item.start_time:Math.max(0,Math.min(drag.plan.duration_seconds-(drag.edge==='move'?duration:.1),item.start_time+delta));
      const finish=drag.edge==='move'?start+duration:drag.edge==='right'?Math.max(start+.1,Math.min(drag.plan.duration_seconds,end+delta)):Math.max(start+.1,end);
      const updated={...item,start_time:start,origin:'manual' as const,source_clip_id:undefined};
      if('duration' in updated) updated.duration=finish-start;
      if('end_time' in updated){
        updated.end_time=finish;
        const shift=drag.edge==='move'?start-item.start_time:0;
        updated.words=updated.words?.map(w=>({...w,start:Math.max(start,w.start+shift),end:Math.min(finish,w.end+shift)})).filter(w=>w.end>w.start);
      }
      if('source_start' in updated && drag.edge==='left') updated.source_start=Math.max(0,(item as {source_start?:number}).source_start||0)+start-item.start_time;
      return updated;
    });
    drag.last={...drag.plan,[drag.key]:items};onUpdatePlan(drag.last,false);
  };
  const endOverlayDrag = (event:React.PointerEvent<HTMLElement>) => {
    const drag=overlayDrag.current;if(!drag)return;
    event.stopPropagation();onUpdatePlan(event.type==='pointercancel'?drag.plan:drag.last,true);overlayDrag.current=null;
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  };
  useEffect(() => () => {
    if (seekFrameRef.current !== null) cancelAnimationFrame(seekFrameRef.current);
    scrubRef.current = null;
  }, []);
  const flushSeek = () => {
    if (seekFrameRef.current !== null) cancelAnimationFrame(seekFrameRef.current);
    seekFrameRef.current = null;
    if (pendingSeekRef.current !== null) {
      onSeekRef.current(pendingSeekRef.current);
      pendingSeekRef.current = null;
    }
  };
  const queueScrub = (clientX: number) => {
    const scroller = scrollContainerRef.current;
    if (!scroller || !scrubRef.current) return;
    const x = clientX - scroller.getBoundingClientRect().left + scroller.scrollLeft
      - timelineOrigin - scrubRef.current.grabOffset;
    pendingSeekRef.current = Math.max(0, Math.min(totalDuration, x / pxPerSec));
    scrubRef.current.lastTime = pendingSeekRef.current;
    if (seekFrameRef.current === null) seekFrameRef.current = requestAnimationFrame(flushSeek);
  };
  const startScrub = (event: React.PointerEvent<HTMLElement>, fromPlayhead = false) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const scroller = scrollContainerRef.current;
    if (!scroller) return;
    const headX = scroller.getBoundingClientRect().left - scroller.scrollLeft
      + timelineOrigin + currentTime * pxPerSec;
    scrubRef.current = { pointerId: event.pointerId, grabOffset: fromPlayhead ? event.clientX - headX : 0, initialTime: currentTime, lastTime: currentTime };
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsScrubbing(true);
    if (!fromPlayhead) queueScrub(event.clientX);
  };
  const moveScrub = (event: React.PointerEvent<HTMLElement>) => {
    if (scrubRef.current?.pointerId !== event.pointerId) return;
    event.stopPropagation();
    queueScrub(event.clientX);
  };
  const endScrub = (event: React.PointerEvent<HTMLElement>) => {
    if (scrubRef.current?.pointerId !== event.pointerId) return;
    event.stopPropagation();
    if (event.type === 'pointerup') queueScrub(event.clientX);
    flushSeek();
    if (event.type === 'pointerup') onScrubCommit?.(scrubRef.current.initialTime, scrubRef.current.lastTime);
    else onSeekRef.current(scrubRef.current.initialTime);
    scrubRef.current = null;
    setIsScrubbing(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const clips = plan.clips;
  const clipCount = clips.length;
  const totalDuration = Math.max(1.0, plan.duration_seconds);

  // Base pixels per second scaled by zoom
  const pxPerSec = Math.max(35, 75 * zoomLevel);
  const timelineContentWidth = Math.max(800, totalDuration * pxPerSec);

  // Decode audio file with Web Audio API to generate authentic waveform peaks
  useEffect(() => {
    if (!audio || !audio.url) {
      setWaveformPeaks(null);
      return;
    }

    let isCancelled = false;
    const abort = new AbortController();
    let audioContext: AudioContext | null = null;
    setWaveformPeaks(null);
    const fetchAndDecode = async () => {
      try {
        const audioUrl = getMediaUrl(audio.url);
        const res = await fetch(audioUrl, { signal: abort.signal });
        if (!res.ok) throw new Error('Audio waveform unavailable');
        const arrayBuf = await res.arrayBuffer();
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (!AudioCtx) return;
        const ctx: AudioContext = new AudioCtx();
        audioContext = ctx;
        const decoded = await ctx.decodeAudioData(arrayBuf);
        if (isCancelled) return;

        const raw = decoded.getChannelData(0);
        const numPeaks = 240;
        const blockSize = Math.max(1, Math.floor(raw.length / numPeaks));
        const peaks: number[] = [];

        for (let i = 0; i < numPeaks; i++) {
          let sum = 0;
          for (let j = 0; j < blockSize; j++) {
            sum += Math.abs(raw[i * blockSize + j] || 0);
          }
          peaks.push(sum / blockSize);
        }

        const maxPeak = Math.max(...peaks, 0.001);
        const normalized = peaks.map(p => Math.min(1.0, p / maxPeak));
        if (!isCancelled) {
          setWaveformPeaks(normalized);
        }
      } catch (err) {
        if (!isCancelled) console.warn('Could not decode audio waveform:', err);
      } finally {
        if (audioContext && audioContext.state !== 'closed') await audioContext.close();
      }
    };

    fetchAndDecode();
    return () => {
      isCancelled = true;
      abort.abort();
    };
  }, [audio?.url]);

  // Draw waveform on canvas
  useEffect(() => {
    const canvas = waveformCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (waveformPeaks && waveformPeaks.length > 0) {
      const barWidth = w / waveformPeaks.length;
      ctx.fillStyle = '#91a498'; // Rayflow sage waveform

      for (let i = 0; i < waveformPeaks.length; i++) {
        const peak = waveformPeaks[i];
        const barH = Math.max(2, peak * (h - 8));
        const x = i * barWidth;
        const y = (h - barH) / 2;
        ctx.fillRect(x, y, Math.max(1, barWidth - 1), barH);
      }

    }
  }, [waveformPeaks, timelineContentWidth]);

  // Recalculate timeline after any clip duration or order changes
  const applyTimelineUpdate = (updatedClips: ClipConfig[], recordHistory = true): EditingPlan => {
    const updatedPlan = recalculateTimeline(updatedClips, plan.transitions || [], plan);
    onUpdatePlan(updatedPlan, recordHistory);
    return updatedPlan;
  };

  // -------------------------------------------------------------
  // Trim Handle Pointer Listeners
  // -------------------------------------------------------------
  const handleTrimPointerDown = (
    e: React.PointerEvent,
    clipId: string,
    edge: 'left' | 'right'
  ) => {
    e.stopPropagation();
    e.preventDefault();

    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);

    const clip = clips.find(c => c.id === clipId);
    if (!clip) return;

    setTrimmingState({
      clipId,
      edge,
      startX: e.clientX,
      initialDuration: clip.duration,
      initialStartTime: clip.start_time,
      initialSourceStart: clip.source_start || 0,
      currentDuration: clip.duration
    });
    pendingTrimPlanRef.current = null;
  };

  const handleTrimPointerMove = (e: React.PointerEvent) => {
    if (!trimmingState) return;
    const deltaPx = e.clientX - trimmingState.startX;
    if (deltaPx === 0) return;
    const deltaSec = Math.round(deltaPx / pxPerSec * 10) / 10;
    const clip = clips.find(c => c.id === trimmingState.clipId);
    const maxDuration = clip?.media_type === 'video'
      ? (trimmingState.edge === 'left' ? trimmingState.initialDuration + trimmingState.initialSourceStart
        : (clip.source_duration ?? Infinity) - trimmingState.initialSourceStart) : 30;
    const minDuration = Math.min(0.5, trimmingState.initialDuration);

    let nextDur = trimmingState.initialDuration;
    if (trimmingState.edge === 'right') {
      nextDur = Math.max(minDuration, Math.min(maxDuration, trimmingState.initialDuration + deltaSec));
    } else {
      nextDur = Math.max(minDuration, Math.min(maxDuration, trimmingState.initialDuration - deltaSec));
    }

    setTrimmingState(prev => prev ? { ...prev, currentDuration: nextDur } : null);

    // Apply real-time preview of clip duration
    const updated = clips.map(c => {
      if (c.id === trimmingState.clipId) {
        if (c.media_type === 'video' && trimmingState.edge === 'left') {
          nextDur = Math.min(nextDur, trimmingState.initialDuration + trimmingState.initialSourceStart);
          return { ...c, duration: nextDur, source_start: trimmingState.initialSourceStart + trimmingState.initialDuration - nextDur };
        }
        return { ...c, duration: nextDur };
      }
      return c;
    });
    pendingTrimPlanRef.current = applyTimelineUpdate(updated, false);
  };

  const handleTrimPointerUp = (e: React.PointerEvent) => {
    if (!trimmingState) return;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // Ignore pointer release errors
    }
    if (pendingTrimPlanRef.current) {
      onUpdatePlan(pendingTrimPlanRef.current, true);
      pendingTrimPlanRef.current = null;
    }
    setTrimmingState(null);
  };

  // -------------------------------------------------------------
  // Drag and Drop Horizontal Reordering with Stable IDs
  // -------------------------------------------------------------
  const handleDragStart = (e: React.DragEvent, clipId: string) => {
    e.dataTransfer.setData('text/plain', clipId);
    e.dataTransfer.effectAllowed = 'move';
    setDraggedClipId(clipId);
  };

  const handleDragOver = (e: React.DragEvent, targetClip: ClipConfig) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const rect = e.currentTarget.getBoundingClientRect();
    const midX = rect.left + rect.width / 2;
    const position: 'before' | 'after' = e.clientX < midX ? 'before' : 'after';

    if (!dragTarget || dragTarget.clipId !== targetClip.id || dragTarget.position !== position) {
      setDragTarget({ clipId: targetClip.id, position });
    }
  };

  const handleDrop = (e: React.DragEvent, targetClip: ClipConfig) => {
    e.preventDefault();
    if (!draggedClipId || draggedClipId === targetClip.id) {
      setDraggedClipId(null);
      setDragTarget(null);
      return;
    }

    const position = dragTarget?.position || 'before';
    const reorderedClips = reorderClips(clips, draggedClipId, targetClip.id, position);
    applyTimelineUpdate(reorderedClips, true);

    setDraggedClipId(null);
    setDragTarget(null);
  };

  const handleDragEnd = () => {
    setDraggedClipId(null);
    setDragTarget(null);
  };

  // Selected clip object for inspector
  const activeSelectedClip = clips.find(c => c.id === selectedClipId) || null;

  // Selected clip duration adjustment via buttons
  const handleAdjustDuration = (delta: number) => {
    if (!activeSelectedClip) return;
    const maxDuration = activeSelectedClip.media_type === 'video'
      ? (activeSelectedClip.source_duration ?? Infinity) - (activeSelectedClip.source_start ?? 0) : 30;
    const newDur = Math.max(Math.min(0.5, activeSelectedClip.duration), Math.min(maxDuration, activeSelectedClip.duration + delta));
    const updated = clips.map(c => (c.id === activeSelectedClip.id ? { ...c, duration: newDur } : c));
    applyTimelineUpdate(updated);
  };

  // Delete selected clip
  const handleDeleteSelected = () => {
    if (!activeSelectedClip) return;
    const updated = clips.filter(c => c.id !== activeSelectedClip.id);
    onSelectClip(null);
    applyTimelineUpdate(updated);
  };

  // Update motion for selected clip
  const handleUpdateMotion = (motion: string) => {
    if (!activeSelectedClip) return;
    const updated = clips.map(c => (c.id === activeSelectedClip.id ? { ...c, motion: motion as any } : c));
    onUpdatePlan({ ...plan, clips: updated });
  };

  // Generate ruler tick values
  const rulerTicks: number[] = [];
  const tickStep = zoomLevel > 1.8 ? 0.5 : 1.0;
  for (let t = 0; t <= totalDuration + 1; t += tickStep) {
    rulerTicks.push(t);
  }

  return (
    <footer className="h-52 max-h-[34dvh] min-h-[140px] border-t border-studio-border bg-studio-panel flex flex-col shrink-0 z-20 select-none">
      {/* 1. TIMELINE TOP BAR / INSPECTOR / ZOOM CONTROLS */}
      <div className="h-10 shrink-0 overflow-x-auto gap-4 border-b border-studio-border px-4 flex items-center justify-between text-xs bg-studio-raised/80">
        {/* Left: Clips Counter & Active Inspector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-studio-text">
            <span className="font-semibold tracking-wider">YOUR EDIT</span>
            <span className="text-studio-quiet">•</span>
            <span className="text-studio-muted">{clipCount} CLIPS</span>
            <span className="text-studio-quiet">•</span>
            <span className="text-studio-muted">{totalDuration.toFixed(1)}s</span>
          </div>

          {activeSelectedClip && (
            <div className="flex items-center gap-2 pl-3 border-l border-studio-border">
              <span className="text-xs font-semibold text-studio-text">
                {activeSelectedClip.id}
              </span>

              {/* Quick +/- Duration */}
              <div className="flex items-center gap-1 bg-studio-panel border border-studio-border rounded px-1 py-0.5 shadow-2xs">
                <button
                  onClick={() => handleAdjustDuration(-0.5)}
                  className="p-0.5 text-studio-muted hover:text-studio-text hover:bg-studio-hover rounded"
                  title="Shorten clip by 0.5s"
                >
                  <Minus className="w-3 h-3" />
                </button>
                <span className="font-mono font-semibold text-[11px] px-1 text-studio-text">
                  {activeSelectedClip.duration.toFixed(1)}s
                </span>
                <button
                  onClick={() => handleAdjustDuration(0.5)}
                  className="p-0.5 text-studio-muted hover:text-studio-text hover:bg-studio-hover rounded"
                  title="Lengthen clip by 0.5s"
                >
                  <Plus className="w-3 h-3" />
                </button>
              </div>

              {/* Motion selector */}
              <select
                value={activeSelectedClip.motion}
                onChange={e => handleUpdateMotion(e.target.value)}
                className="text-xs bg-studio-panel border border-studio-border rounded px-2 py-0.5 text-studio-text font-medium outline-none shadow-2xs"
              >
                <option value="zoom_in">Zoom In</option>
                <option value="zoom_out">Zoom Out</option>
                <option value="pan_left">Pan Left</option>
                <option value="pan_right">Pan Right</option>
                <option value="static">Static</option>
              </select>

              {/* Delete Clip */}
              <button
                onClick={handleDeleteSelected}
                className="p-1 text-studio-quiet hover:text-danger transition-colors ml-1"
                title="Remove clip from timeline"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        {/* Right: Zoom Controls */}
        <div className="flex items-center gap-2 text-xs text-studio-muted">
          <button
            onClick={() => setZoomLevel(prev => Math.max(0.75, Math.round((prev - 0.25) * 100) / 100))}
            disabled={zoomLevel <= 0.75}
            className="p-1 rounded border border-studio-border bg-studio-panel hover:bg-studio-hover disabled:opacity-30 disabled:pointer-events-none text-studio-text shadow-2xs"
            title="Zoom Out Timeline"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>

          <input
            type="range"
            min="0.75"
            max="3.0"
            step="0.25"
            value={zoomLevel}
            onChange={e => setZoomLevel(parseFloat(e.target.value))}
            className="w-18 accent-accent h-1 bg-studio-line rounded cursor-pointer"
            title="Timeline Zoom Level"
          />

          <button
            onClick={() => setZoomLevel(prev => Math.min(3.0, Math.round((prev + 0.25) * 100) / 100))}
            disabled={zoomLevel >= 3.0}
            className="p-1 rounded border border-studio-border bg-studio-panel hover:bg-studio-hover disabled:opacity-30 disabled:pointer-events-none text-studio-text shadow-2xs"
            title="Zoom In Timeline"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setZoomLevel(1.0)}
            className="px-2 py-0.5 rounded border border-studio-border bg-studio-panel hover:bg-studio-hover font-mono text-[10px] text-studio-text shadow-2xs"
            title="Reset Zoom to 100%"
          >
            {(zoomLevel * 100).toFixed(0)}%
          </button>
        </div>
      </div>

      {/* 2. TIMELINE TRACKS SCROLL CONTAINER */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-auto relative bg-studio-raised/50"
      >
        <div
          style={{ width: `${timelineContentWidth + 42}px` }}
          className="relative min-h-full flex flex-col p-2 space-y-1"
        >
          {/* PLAYHEAD NEEDLE */}
          <div
            style={{
              left: `${currentTime * pxPerSec + timelineOrigin}px`,
              transform: 'translateX(-50%)'
            }}
            role="slider" tabIndex={0} aria-label="Timeline playhead"
            aria-valuemin={0} aria-valuemax={totalDuration} aria-valuenow={currentTime}
            aria-valuetext={currentTime.toFixed(2) + ' seconds'}
            onPointerDown={e => startScrub(e, true)} onPointerMove={moveScrub}
            onPointerUp={endScrub} onPointerCancel={endScrub} onLostPointerCapture={endScrub}
            onKeyDown={e => {
              const next = e.key === 'Home' ? 0 : e.key === 'End' ? totalDuration
                : e.key === 'ArrowLeft' ? currentTime - (e.shiftKey ? 1 : 1 / 30)
                : e.key === 'ArrowRight' ? currentTime + (e.shiftKey ? 1 : 1 / 30) : null;
              if (next !== null) { e.preventDefault(); onSeek(Math.max(0, Math.min(totalDuration, next))); }
            }}
            className={`absolute top-0 bottom-0 w-5 touch-none z-40 flex flex-col items-center outline-offset-2 focus-visible:outline ${isScrubbing ? 'cursor-grabbing' : 'cursor-ew-resize'}`}
          >
            {/* Playhead badge */}
            <div className="w-3 h-3 bg-accent rotate-45 rounded-2xs shadow-xs" />
            <div className="w-0.5 flex-1 bg-accent" />
          </div>

          {/* TIME RULER */}
          <div
            onPointerDown={e => startScrub(e)} onPointerMove={moveScrub}
            onPointerUp={endScrub} onPointerCancel={endScrub} onLostPointerCapture={endScrub}
            className="h-5 shrink-0 touch-none flex items-center relative cursor-pointer border-b border-studio-border pl-6"
            title="Click or drag on ruler to seek"
          >
            {rulerTicks.map(t => {
              const isSecond = Number.isInteger(t);
              const xPos = t * pxPerSec;
              return (
                <div
                  key={t}
                  style={{ left: `${xPos + 25}px` }}
                  className="absolute top-0 bottom-0 flex flex-col items-start"
                >
                  <div
                    className={`w-px ${
                      isSecond ? 'h-2.5 bg-studio-quiet' : 'h-1.5 bg-studio-border'
                    }`}
                  />
                  {isSecond && (
                    <span className="text-[9px] font-mono text-studio-muted pl-0.5 -mt-0.5">
                      {Math.floor(t / 60)}:{(t % 60).toString().padStart(2, '0')}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* VIDEO / IMAGES TRACK */}
          <div className="h-16 flex items-center relative">
            <span className="text-[9px] font-mono font-semibold text-studio-quiet uppercase w-6 shrink-0 text-center">
              V1
            </span>

            <div className="flex-1 h-full relative rounded-lg border border-studio-border bg-studio-panel overflow-visible shadow-2xs">
              {clipCount === 0 ? (
                <div className="h-full flex items-center px-4 text-xs text-studio-quiet italic">
                  Your Rayflow timeline is ready. Add footage to start shaping your story.
                </div>
              ) : (
                clips.map((clip, i) => {
                  const isSelected = selectedClipId === clip.id;
                  const isDraggingOver = dragTarget?.clipId === clip.id;
                  const leftPx = clip.start_time * pxPerSec;
                  const widthPx = clip.duration * pxPerSec;

                  // Transition badge with next clip
                  const nextClip = clips[i + 1];
                  const boundaryTrans = nextClip
                    ? (plan.transitions || []).find(t => t.from_clip_id === clip.id && t.to_clip_id === nextClip.id)
                    : null;
                  const hasActiveTrans = boundaryTrans && boundaryTrans.enabled && boundaryTrans.type !== 'none';

                  return (
                    <React.Fragment key={clip.id}>
                      {/* Drop insertion line indicator */}
                      {isDraggingOver && (
                        <div
                          style={{
                            left: `${dragTarget.position === 'before' ? leftPx : leftPx + widthPx}px`
                          }}
                          className="absolute top-0 bottom-0 w-1 bg-accent z-30 pointer-events-none rounded shadow-xs"
                        />
                      )}

                      {/* CLIP BLOCK */}
                      <div
                        draggable={!trimmingState && !isScrubbing}
                        data-clip-id={clip.id}
                        tabIndex={0}
                        role="button"
                        aria-label={`Select clip: ${clip.label || clip.id}`}
                        aria-pressed={selectedClipId === clip.id}
                        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectClip(clip.id); onSeek(clip.start_time); } }}
                        onDragStart={e => handleDragStart(e, clip.id)}
                        onDragOver={e => handleDragOver(e, clip)}
                        onDrop={e => handleDrop(e, clip)}
                        onDragEnd={handleDragEnd}
                        onClick={e => {
                          e.stopPropagation();
                          e.currentTarget.focus();
                          onSelectClip(clip.id);
                          onSeek(clip.start_time);
                        }}
                        style={{
                          left: `${leftPx}px`,
                          width: `${widthPx}px`
                        }}
                        className={`absolute top-1 bottom-1 rounded-md overflow-hidden cursor-grab active:cursor-grabbing border transition-shadow ${
                          isSelected
                            ? 'border-accent ring-2 ring-accent shadow-md z-10'
                            : 'border-studio-border hover:border-studio-border shadow-2xs'
                        }`}
                      >
                        {/* LEFT TRIM HANDLE */}
                        <div
                          onPointerDown={e => handleTrimPointerDown(e, clip.id, 'left')}
                          onPointerMove={handleTrimPointerMove}
                          onPointerUp={handleTrimPointerUp}
                          onPointerCancel={handleTrimPointerUp}
                          onClick={e => e.stopPropagation()}
                          style={{ touchAction: 'none' }}
                          className="absolute left-0 top-0 bottom-0 w-2.5 cursor-ew-resize hover:bg-studio-canvas/40 z-20 flex items-center justify-center group/handle"
                          title="Drag left edge to trim start"
                        >
                          <div className="w-1 h-3 rounded-full bg-studio-text/70 group-hover/handle:bg-studio-text" />
                        </div>

                        {/* RIGHT TRIM HANDLE */}
                        <div
                          onPointerDown={e => handleTrimPointerDown(e, clip.id, 'right')}
                          onPointerMove={handleTrimPointerMove}
                          onPointerUp={handleTrimPointerUp}
                          onPointerCancel={handleTrimPointerUp}
                          onClick={e => e.stopPropagation()}
                          style={{ touchAction: 'none' }}
                          className="absolute right-0 top-0 bottom-0 w-2.5 cursor-ew-resize hover:bg-studio-canvas/40 z-20 flex items-center justify-center group/handle"
                          title="Drag right edge to trim duration"
                        >
                          <div className="w-1 h-3 rounded-full bg-studio-text/70 group-hover/handle:bg-studio-text" />
                        </div>

                        {/* Thumbnail background */}
                        {clip.media_type === 'video' ? (
                          <video src={getMediaUrl(clip.image_url)} muted preload="metadata" className="w-full h-full object-cover pointer-events-none" />
                        ) : (
                          <img src={getMediaUrl(clip.image_url)} alt="" draggable={false} className="w-full h-full object-cover pointer-events-none" />
                        )}

                        {/* Bottom clip duration badge */}
                        <div className="absolute inset-x-0 bottom-0 bg-studio-canvas/70 flex items-end justify-between p-1 text-[9px] font-mono text-white pointer-events-none">
                          <span className="font-semibold">
                            {trimmingState?.clipId === clip.id
                              ? `${trimmingState.currentDuration.toFixed(1)}s`
                              : `${clip.duration.toFixed(1)}s`}
                          </span>
                          <span className="text-[8px] bg-studio-canvas/80 px-1 py-0.2 rounded uppercase">
                            {clip.motion}
                          </span>
                        </div>
                      </div>

                      {/* BOUNDARY TRANSITION BADGE */}
                      {i < clipCount - 1 && nextClip && (
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            if (onOpenEffectsForBoundary) {
                              onOpenEffectsForBoundary(clip.id, nextClip.id);
                            }
                          }}
                          style={{
                            left: `${leftPx + widthPx - 8}px`
                          }}
                          className={`absolute top-4 w-4 h-4 rounded-full flex items-center justify-center z-25 text-[8px] font-bold shadow-xs border transition-transform hover:scale-110 ${
                            hasActiveTrans
                              ? 'bg-accent text-white border-white'
                              : 'bg-studio-hover text-studio-muted border-studio-border hover:bg-studio-line'
                          }`}
                          title={`Transition: ${
                            hasActiveTrans ? boundaryTrans?.type.replace('_', ' ') : 'None (Cut)'
                          }. Click to edit in Effects.`}
                        >
                          {hasActiveTrans ? '⧖' : '·'}
                        </button>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </div>
          </div>

          {/* VISUAL INSERTS TRACK (V2) */}
          {plan.visual_inserts && plan.visual_inserts.length > 0 && (
            <div className="h-8 flex items-center relative">
              <span className="text-[9px] font-mono font-semibold text-jade uppercase w-6 shrink-0 text-center">
                V2
              </span>
              <div className="flex-1 h-full relative rounded-lg border border-jade-border/80 bg-jade-soft/40 overflow-hidden shadow-2xs">
                {plan.visual_inserts.map(ins => {
                  const leftPx = ins.start_time * pxPerSec;
                  const widthPx = Math.max(16, ins.duration * pxPerSec);
                  const isCurrent = currentTime >= ins.start_time && currentTime <= ins.start_time + ins.duration;
                  return (
                    <div
                      key={ins.id}
                      data-insert-id={ins.id}
                      onPointerDown={e=>startOverlayDrag(e,'visual_inserts',ins.id)}
                      onPointerMove={moveOverlayDrag}
                      onPointerUp={endOverlayDrag}
                      onPointerCancel={endOverlayDrag}
                      onClick={e => {
                        e.stopPropagation();
                        onSeek(ins.start_time);
                      }}
                      style={{
                        left: `${leftPx}px`,
                        width: `${widthPx}px`, touchAction:'none'
                      }}
                      className={`absolute top-0.5 bottom-0.5 rounded px-1.5 flex items-center justify-between text-[10px] font-medium border cursor-pointer transition-all truncate ${
                        isCurrent
                          ? 'bg-jade text-ink border-jade-border shadow-xs ring-1 ring-jade-border'
                          : 'bg-jade-soft text-jade border-jade-border hover:bg-jade-soft'
                      }`}
                      title={`Insert: ${ins.mode.toUpperCase()} (${ins.start_time.toFixed(1)}s - ${(ins.start_time + ins.duration).toFixed(1)}s). Click to seek.`}
                    >
                      <span className="absolute inset-y-0 left-0 w-2 cursor-ew-resize" onPointerDown={e=>startOverlayDrag(e,'visual_inserts',ins.id,'left')} />
                      <span className="truncate pointer-events-none">{ins.label || ins.mode.toUpperCase()}</span>
                      <span className="absolute inset-y-0 right-0 w-2 cursor-ew-resize" onPointerDown={e=>startOverlayDrag(e,'visual_inserts',ins.id,'right')} />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SUBTITLES / CAPTIONS TRACK (CC) */}
          {plan.subtitles && plan.subtitles.length > 0 && (
            <div className="h-8 flex items-center relative">
              <span className="text-[9px] font-mono font-semibold text-brass uppercase w-6 shrink-0 text-center">
                CC
              </span>
              <div className="flex-1 h-full relative rounded-lg border border-brass-border/80 bg-brass-soft/40 overflow-hidden shadow-2xs">
                {plan.subtitles.map(sub => {
                  const leftPx = sub.start_time * pxPerSec;
                  const widthPx = Math.max(16, (sub.end_time - sub.start_time) * pxPerSec);
                  const isCurrent = currentTime >= sub.start_time && currentTime <= sub.end_time;
                  return (
                    <div
                      key={sub.id}
                      data-subtitle-id={sub.id}
                      tabIndex={0}
                      role="button"
                      aria-label={`Select caption: ${sub.text}`}
                      aria-pressed={selectedCaptionIds.includes(sub.id)}
                      onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelectCaption?.(sub.id, event.shiftKey || event.ctrlKey || event.metaKey); onSeek(sub.start_time); } }}
                      onPointerDown={e=>startOverlayDrag(e,'subtitles',sub.id)}
                      onPointerMove={moveOverlayDrag}
                      onPointerUp={endOverlayDrag}
                      onPointerCancel={endOverlayDrag}
                      onClick={e => {
                        e.stopPropagation();
                        onSeek(sub.start_time);
                      }}
                      style={{
                        left: `${leftPx}px`,
                        width: `${widthPx}px`, touchAction:'none'
                      }}
                      className={`absolute top-0.5 bottom-0.5 rounded px-1 flex items-center justify-between text-[10px] font-medium border cursor-pointer transition-all truncate ${
                        selectedCaptionIds.includes(sub.id) || isCurrent
                          ? 'bg-brass text-ink border-brass-border shadow-xs ring-1 ring-brass-border'
                          : 'bg-brass-soft/90 text-brass border-brass-border hover:bg-brass-soft'
                      }`}
                      title={`"${sub.text}" (${sub.start_time.toFixed(1)}s - ${sub.end_time.toFixed(1)}s). Click to seek.`}
                    >
                      <span className="absolute inset-y-0 left-0 w-2 cursor-ew-resize" onPointerDown={e=>startOverlayDrag(e,'subtitles',sub.id,'left')} />
                      <span className="truncate pointer-events-none">{sub.text}</span>
                      <span className="absolute inset-y-0 right-0 w-2 cursor-ew-resize" onPointerDown={e=>startOverlayDrag(e,'subtitles',sub.id,'right')} />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!!plan.sound_cues?.length && <div className="h-8 flex items-center relative">
            <span className="text-[9px] font-mono w-6 shrink-0 text-center text-studio-muted">A2</span>
            <div className="flex-1 h-full relative rounded-lg border border-studio-border bg-studio-hover overflow-hidden">
              {plan.sound_cues.map(cue=><div key={cue.id} data-cue-id={cue.id} title={`${cue.label} · ${cue.start_time.toFixed(2)}s`}
                onPointerDown={e=>startOverlayDrag(e,'sound_cues',cue.id)} onPointerMove={moveOverlayDrag} onPointerUp={endOverlayDrag} onPointerCancel={endOverlayDrag}
                style={{left:cue.start_time*pxPerSec,width:Math.max(14,.1*pxPerSec),touchAction:'none'}}
                className={`absolute top-1 bottom-1 rounded cursor-ew-resize ${cue.muted||plan.list_sounds===false?'bg-studio-border':'bg-jade'}`} />)}
            </div>
          </div>}
          {/* AUDIO TRACK (AUD) */}
          <div className="h-12 flex items-center relative">
            <span className="text-[9px] font-mono font-semibold text-studio-quiet uppercase w-6 shrink-0 text-center">
              A1
            </span>

            <div tabIndex={audio ? 0 : undefined} role={audio ? 'button' : undefined} aria-label={audio ? 'Select audio track' : undefined} aria-pressed={audio ? audioSelected : undefined}
              onClick={event => { if (audio) { event.stopPropagation(); event.currentTarget.focus(); onSelectAudio?.(); } }}
              onKeyDown={event => { if (audio && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onSelectAudio?.(); } }}
              className={`flex-1 h-full relative rounded-lg border ${audioSelected ? 'border-accent' : 'border-studio-border'} bg-studio-panel overflow-hidden shadow-2xs flex items-center`}>
              {/* Waveform HTML5 Canvas */}
              <canvas
                ref={waveformCanvasRef}
                width={Math.round(timelineContentWidth)}
                height={44}
                className="w-full h-full object-fill absolute inset-0 pointer-events-none"
              />

              {/* Librosa Beat Markers */}
              {audioAnalysis && audioAnalysis.beat_times.length > 0 && (
                <div className="absolute inset-0 pointer-events-none">
                  {audioAnalysis.beat_times
                    .filter(b => b <= totalDuration)
                    .map((beatTime, idx) => {
                      const xPos = beatTime * pxPerSec;
                      const isStrong = audioAnalysis.strong_beats.includes(beatTime);
                      return (
                        <div
                          key={idx}
                          style={{ left: `${xPos}px` }}
                          className={`absolute top-0 bottom-0 ${
                            isStrong ? 'w-0.5 bg-studio-canvas/80' : 'w-px bg-studio-quiet/60'
                          }`}
                          title={`Beat at ${beatTime}s`}
                        />
                      );
                    })}
                </div>
              )}

              {/* Audio Track Info Bar */}
              <div className="relative z-10 px-3 flex items-center justify-between w-full text-[11px] font-mono text-studio-text pointer-events-none">
                <span className="font-semibold truncate max-w-[260px]">
                  {audio ? audio.original_name : 'Add music to find your rhythm'}
                </span>
                <span className="text-[10px] font-semibold text-studio-muted bg-studio-panel/80 px-1.5 py-0.5 rounded border border-studio-border">
                  {audioAnalysis?.tempo ? `${audioAnalysis.tempo} BPM` : 'No beat data'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
};
