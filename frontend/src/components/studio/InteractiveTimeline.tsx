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
    overlayDrag.current={key,id,edge,x:event.clientX,plan,last:plan};
  };
  const moveOverlayDrag = (event:React.PointerEvent<HTMLElement>) => {
    const drag=overlayDrag.current;if(!drag)return;event.preventDefault();event.stopPropagation();
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
      ctx.fillStyle = '#A1A1AA'; // Zinc-400

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
    <footer className="h-52 max-h-[34dvh] min-h-[140px] border-t border-zinc-200 bg-white flex flex-col shrink-0 z-20 select-none">
      {/* 1. TIMELINE TOP BAR / INSPECTOR / ZOOM CONTROLS */}
      <div className="h-10 shrink-0 overflow-x-auto gap-4 border-b border-zinc-200 px-4 flex items-center justify-between text-xs bg-zinc-50/80">
        {/* Left: Clips Counter & Active Inspector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-zinc-800">
            <span className="font-semibold tracking-wider">TIMELINE</span>
            <span className="text-zinc-400">•</span>
            <span className="text-zinc-600">{clipCount} CLIPS</span>
            <span className="text-zinc-400">•</span>
            <span className="text-zinc-600">{totalDuration.toFixed(1)}s</span>
          </div>

          {activeSelectedClip && (
            <div className="flex items-center gap-2 pl-3 border-l border-zinc-300">
              <span className="text-xs font-semibold text-zinc-900">
                {activeSelectedClip.id}
              </span>

              {/* Quick +/- Duration */}
              <div className="flex items-center gap-1 bg-white border border-zinc-200 rounded px-1 py-0.5 shadow-2xs">
                <button
                  onClick={() => handleAdjustDuration(-0.5)}
                  className="p-0.5 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded"
                  title="Shorten clip by 0.5s"
                >
                  <Minus className="w-3 h-3" />
                </button>
                <span className="font-mono font-semibold text-[11px] px-1 text-zinc-900">
                  {activeSelectedClip.duration.toFixed(1)}s
                </span>
                <button
                  onClick={() => handleAdjustDuration(0.5)}
                  className="p-0.5 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded"
                  title="Lengthen clip by 0.5s"
                >
                  <Plus className="w-3 h-3" />
                </button>
              </div>

              {/* Motion selector */}
              <select
                value={activeSelectedClip.motion}
                onChange={e => handleUpdateMotion(e.target.value)}
                className="text-xs bg-white border border-zinc-200 rounded px-2 py-0.5 text-zinc-800 font-medium outline-none shadow-2xs"
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
                className="p-1 text-zinc-400 hover:text-red-600 transition-colors ml-1"
                title="Remove clip from timeline"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        {/* Right: Zoom Controls */}
        <div className="flex items-center gap-2 text-xs text-zinc-600">
          <button
            onClick={() => setZoomLevel(prev => Math.max(0.75, Math.round((prev - 0.25) * 100) / 100))}
            disabled={zoomLevel <= 0.75}
            className="p-1 rounded border border-zinc-200 bg-white hover:bg-zinc-100 disabled:opacity-30 disabled:pointer-events-none text-zinc-700 shadow-2xs"
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
            className="w-18 accent-zinc-900 h-1 bg-zinc-200 rounded cursor-pointer"
            title="Timeline Zoom Level"
          />

          <button
            onClick={() => setZoomLevel(prev => Math.min(3.0, Math.round((prev + 0.25) * 100) / 100))}
            disabled={zoomLevel >= 3.0}
            className="p-1 rounded border border-zinc-200 bg-white hover:bg-zinc-100 disabled:opacity-30 disabled:pointer-events-none text-zinc-700 shadow-2xs"
            title="Zoom In Timeline"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setZoomLevel(1.0)}
            className="px-2 py-0.5 rounded border border-zinc-200 bg-white hover:bg-zinc-100 font-mono text-[10px] text-zinc-700 shadow-2xs"
            title="Reset Zoom to 100%"
          >
            {(zoomLevel * 100).toFixed(0)}%
          </button>
        </div>
      </div>

      {/* 2. TIMELINE TRACKS SCROLL CONTAINER */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-auto relative bg-zinc-50/50"
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
            <div className="w-3 h-3 bg-zinc-900 rotate-45 rounded-2xs shadow-xs" />
            <div className="w-0.5 flex-1 bg-zinc-900" />
          </div>

          {/* TIME RULER */}
          <div
            onPointerDown={e => startScrub(e)} onPointerMove={moveScrub}
            onPointerUp={endScrub} onPointerCancel={endScrub} onLostPointerCapture={endScrub}
            className="h-5 shrink-0 touch-none flex items-center relative cursor-pointer border-b border-zinc-200 pl-6"
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
                      isSecond ? 'h-2.5 bg-zinc-400' : 'h-1.5 bg-zinc-300'
                    }`}
                  />
                  {isSecond && (
                    <span className="text-[9px] font-mono text-zinc-500 pl-0.5 -mt-0.5">
                      {Math.floor(t / 60)}:{(t % 60).toString().padStart(2, '0')}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* VIDEO / IMAGES TRACK */}
          <div className="h-16 flex items-center relative">
            <span className="text-[9px] font-mono font-semibold text-zinc-400 uppercase w-6 shrink-0 text-center">
              V1
            </span>

            <div className="flex-1 h-full relative rounded-lg border border-zinc-200 bg-white overflow-visible shadow-2xs">
              {clipCount === 0 ? (
                <div className="h-full flex items-center px-4 text-xs text-zinc-400 italic">
                  No photographs on timeline. Upload photos from the sidebar to assemble reel.
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
                          className="absolute top-0 bottom-0 w-1 bg-zinc-900 z-30 pointer-events-none rounded shadow-xs"
                        />
                      )}

                      {/* CLIP BLOCK */}
                      <div
                        draggable={!trimmingState && !isScrubbing}
                        data-clip-id={clip.id}
                        onDragStart={e => handleDragStart(e, clip.id)}
                        onDragOver={e => handleDragOver(e, clip)}
                        onDrop={e => handleDrop(e, clip)}
                        onDragEnd={handleDragEnd}
                        onClick={e => {
                          e.stopPropagation();
                          onSelectClip(clip.id);
                          onSeek(clip.start_time);
                        }}
                        style={{
                          left: `${leftPx}px`,
                          width: `${widthPx}px`
                        }}
                        className={`absolute top-1 bottom-1 rounded-md overflow-hidden cursor-grab active:cursor-grabbing border transition-shadow ${
                          isSelected
                            ? 'border-zinc-900 ring-2 ring-zinc-900 shadow-md z-10'
                            : 'border-zinc-300 hover:border-zinc-500 shadow-2xs'
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
                          className="absolute left-0 top-0 bottom-0 w-2.5 cursor-ew-resize hover:bg-zinc-900/40 z-20 flex items-center justify-center group/handle"
                          title="Drag left edge to trim start"
                        >
                          <div className="w-1 h-3 rounded-full bg-white/70 group-hover/handle:bg-white" />
                        </div>

                        {/* RIGHT TRIM HANDLE */}
                        <div
                          onPointerDown={e => handleTrimPointerDown(e, clip.id, 'right')}
                          onPointerMove={handleTrimPointerMove}
                          onPointerUp={handleTrimPointerUp}
                          onPointerCancel={handleTrimPointerUp}
                          onClick={e => e.stopPropagation()}
                          style={{ touchAction: 'none' }}
                          className="absolute right-0 top-0 bottom-0 w-2.5 cursor-ew-resize hover:bg-zinc-900/40 z-20 flex items-center justify-center group/handle"
                          title="Drag right edge to trim duration"
                        >
                          <div className="w-1 h-3 rounded-full bg-white/70 group-hover/handle:bg-white" />
                        </div>

                        {/* Thumbnail background */}
                        {clip.media_type === 'video' ? (
                          <video src={getMediaUrl(clip.image_url)} muted preload="metadata" className="w-full h-full object-cover pointer-events-none" />
                        ) : (
                          <img src={getMediaUrl(clip.image_url)} alt="" draggable={false} className="w-full h-full object-cover pointer-events-none" />
                        )}

                        {/* Bottom clip duration badge */}
                        <div className="absolute inset-x-0 bottom-0 bg-zinc-950/70 flex items-end justify-between p-1 text-[9px] font-mono text-white pointer-events-none">
                          <span className="font-semibold">
                            {trimmingState?.clipId === clip.id
                              ? `${trimmingState.currentDuration.toFixed(1)}s`
                              : `${clip.duration.toFixed(1)}s`}
                          </span>
                          <span className="text-[8px] bg-zinc-900/80 px-1 py-0.2 rounded uppercase">
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
                              ? 'bg-zinc-900 text-white border-white'
                              : 'bg-zinc-100 text-zinc-500 border-zinc-300 hover:bg-zinc-200'
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
              <span className="text-[9px] font-mono font-semibold text-blue-500 uppercase w-6 shrink-0 text-center">
                V2
              </span>
              <div className="flex-1 h-full relative rounded-lg border border-blue-200/80 bg-blue-50/40 overflow-hidden shadow-2xs">
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
                          ? 'bg-blue-500 text-white border-blue-600 shadow-xs ring-1 ring-blue-400'
                          : 'bg-blue-100 text-blue-900 border-blue-300 hover:bg-blue-200'
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
              <span className="text-[9px] font-mono font-semibold text-amber-500 uppercase w-6 shrink-0 text-center">
                CC
              </span>
              <div className="flex-1 h-full relative rounded-lg border border-amber-200/80 bg-amber-50/40 overflow-hidden shadow-2xs">
                {plan.subtitles.map(sub => {
                  const leftPx = sub.start_time * pxPerSec;
                  const widthPx = Math.max(16, (sub.end_time - sub.start_time) * pxPerSec);
                  const isCurrent = currentTime >= sub.start_time && currentTime <= sub.end_time;
                  return (
                    <div
                      key={sub.id}
                      data-subtitle-id={sub.id}
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
                        isCurrent
                          ? 'bg-amber-400 text-zinc-950 border-amber-500 shadow-xs ring-1 ring-amber-400'
                          : 'bg-amber-100/90 text-amber-900 border-amber-300 hover:bg-amber-200'
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
            <span className="text-[9px] font-mono w-6 shrink-0 text-center text-zinc-500">A2</span>
            <div className="flex-1 h-full relative rounded-lg border border-zinc-300 bg-zinc-100 overflow-hidden">
              {plan.sound_cues.map(cue=><div key={cue.id} data-cue-id={cue.id} title={`${cue.label} · ${cue.start_time.toFixed(2)}s`}
                onPointerDown={e=>startOverlayDrag(e,'sound_cues',cue.id)} onPointerMove={moveOverlayDrag} onPointerUp={endOverlayDrag} onPointerCancel={endOverlayDrag}
                style={{left:cue.start_time*pxPerSec,width:Math.max(14,.1*pxPerSec),touchAction:'none'}}
                className={`absolute top-1 bottom-1 rounded cursor-ew-resize ${cue.muted||plan.list_sounds===false?'bg-zinc-300':'bg-zinc-700'}`} />)}
            </div>
          </div>}
          {/* AUDIO TRACK (AUD) */}
          <div className="h-12 flex items-center relative">
            <span className="text-[9px] font-mono font-semibold text-zinc-400 uppercase w-6 shrink-0 text-center">
              A1
            </span>

            <div className="flex-1 h-full relative rounded-lg border border-zinc-200 bg-white overflow-hidden shadow-2xs flex items-center">
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
                            isStrong ? 'w-0.5 bg-zinc-900/80' : 'w-px bg-zinc-400/60'
                          }`}
                          title={`Beat at ${beatTime}s`}
                        />
                      );
                    })}
                </div>
              )}

              {/* Audio Track Info Bar */}
              <div className="relative z-10 px-3 flex items-center justify-between w-full text-[11px] font-mono text-zinc-700 pointer-events-none">
                <span className="font-semibold truncate max-w-[260px]">
                  {audio ? audio.original_name : 'No soundtrack loaded'}
                </span>
                <span className="text-[10px] font-semibold text-zinc-500 bg-white/80 px-1.5 py-0.5 rounded border border-zinc-200">
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
