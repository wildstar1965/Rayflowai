import React, { useState, useEffect, useRef } from 'react';
import {
  EditingPlan,
  ClipConfig,
  TransitionConfig,
  AudioAnalysisResult,
  UploadedAudio
} from '../../types';
import { getMediaUrl } from '../../services/api';
import {
  Plus,
  Minus,
  Trash2,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Sparkles,
  GripHorizontal,
  Clock
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
  onUpdatePlan: (updatedPlan: EditingPlan) => void;
  onOpenEffectsForBoundary?: (fromClipId: string, toClipId: string) => void;
}

interface TrimmingActiveState {
  clipId: string;
  edge: 'left' | 'right';
  startX: number;
  initialDuration: number;
  initialStartTime: number;
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
  onUpdatePlan,
  onOpenEffectsForBoundary
}) => {
  // Zoom state: 0.75x to 3.0x
  const [zoomLevel, setZoomLevel] = useState<number>(1.0);

  // Trimming interaction state
  const [trimmingState, setTrimmingState] = useState<TrimmingActiveState | null>(null);

  // Drag-and-drop reordering state
  const [draggedClipIndex, setDraggedClipIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // Audio waveform peaks cache
  const [waveformPeaks, setWaveformPeaks] = useState<number[] | null>(null);
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Container refs for scroll sync
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

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
    const fetchAndDecode = async () => {
      try {
        const audioUrl = getMediaUrl(audio.url);
        const res = await fetch(audioUrl);
        const arrayBuf = await res.arrayBuffer();
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const decoded = await ctx.decodeAudioData(arrayBuf);
        if (isCancelled) return;

        const raw = decoded.getChannelData(0);
        const numPeaks = 240;
        const blockSize = Math.floor(raw.length / numPeaks);
        const peaks: number[] = [];

        for (let i = 0; i < numPeaks; i++) {
          let sum = 0;
          for (let j = 0; j < blockSize; j++) {
            sum += Math.abs(raw[i * blockSize + j]);
          }
          peaks.push(sum / blockSize);
        }

        const maxPeak = Math.max(...peaks, 0.001);
        const normalized = peaks.map(p => Math.min(1.0, p / maxPeak));
        if (!isCancelled) {
          setWaveformPeaks(normalized);
        }
      } catch (err) {
        console.warn('Could not decode audio waveform:', err);
      }
    };

    fetchAndDecode();
    return () => {
      isCancelled = true;
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
    } else {
      // Subtle audio placeholder bars if still decoding
      ctx.fillStyle = '#E4E4E7';
      const numBars = 120;
      const barW = w / numBars;
      for (let i = 0; i < numBars; i++) {
        const fakeH = 4 + (Math.sin(i * 0.4) * 0.5 + 0.5) * 14;
        ctx.fillRect(i * barW, (h - fakeH) / 2, barW - 1, fakeH);
      }
    }
  }, [waveformPeaks, timelineContentWidth]);

  // Recalculate timeline after any clip duration or order changes
  const applyTimelineUpdate = (updatedClips: ClipConfig[]) => {
    let accTime = 0.0;
    const synced = updatedClips.map(c => {
      const start = Math.round(accTime * 100) / 100;
      const dur = Math.max(0.5, Math.round(c.duration * 100) / 100);
      accTime += dur;
      return { ...c, start_time: start, duration: dur };
    });

    const newTotal = Math.round(accTime * 100) / 100;

    // Safely clamp boundary transitions
    let updatedTransitions = plan.transitions || [];
    if (updatedTransitions.length > 0 && synced.length > 1) {
      const clipMap = new Map(synced.map(c => [c.id, c]));
      updatedTransitions = updatedTransitions.map(t => {
        const c1 = clipMap.get(t.from_clip_id);
        const c2 = clipMap.get(t.to_clip_id);
        if (c1 && c2) {
          const maxAllowed = Math.max(0.1, Math.min(c1.duration, c2.duration) - 0.1);
          return { ...t, duration: Math.min(t.duration, maxAllowed) };
        }
        return t;
      });
    }

    onUpdatePlan({
      ...plan,
      duration_seconds: newTotal,
      clips: synced,
      transitions: updatedTransitions
    });
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
      currentDuration: clip.duration
    });
  };

  const handleTrimPointerMove = (e: React.PointerEvent) => {
    if (!trimmingState) return;
    const deltaPx = e.clientX - trimmingState.startX;
    const deltaSec = deltaPx / pxPerSec;

    let nextDur = trimmingState.initialDuration;
    if (trimmingState.edge === 'right') {
      nextDur = Math.max(0.5, Math.min(30.0, Math.round((trimmingState.initialDuration + deltaSec) * 10) / 10));
    } else {
      nextDur = Math.max(0.5, Math.min(30.0, Math.round((trimmingState.initialDuration - deltaSec) * 10) / 10));
    }

    setTrimmingState(prev => prev ? { ...prev, currentDuration: nextDur } : null);

    // Apply real-time preview of clip duration
    const updated = clips.map(c => {
      if (c.id === trimmingState.clipId) {
        return { ...c, duration: nextDur };
      }
      return c;
    });
    applyTimelineUpdate(updated);
  };

  const handleTrimPointerUp = (e: React.PointerEvent) => {
    if (!trimmingState) return;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // Ignore pointer release errors
    }
    setTrimmingState(null);
  };

  // -------------------------------------------------------------
  // Drag and Drop Horizontal Reordering
  // -------------------------------------------------------------
  const handleDragStart = (e: React.DragEvent, index: number) => {
    e.dataTransfer.setData('text/plain', String(index));
    e.dataTransfer.effectAllowed = 'move';
    setDraggedClipIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverIndex !== targetIndex) {
      setDragOverIndex(targetIndex);
    }
  };

  const handleDrop = (e: React.DragEvent, dropTargetIndex: number) => {
    e.preventDefault();
    if (draggedClipIndex === null || draggedClipIndex === dropTargetIndex) {
      setDraggedClipIndex(null);
      setDragOverIndex(null);
      return;
    }

    const updatedClips = [...clips];
    const [moved] = updatedClips.splice(draggedClipIndex, 1);
    updatedClips.splice(dropTargetIndex, 0, moved);

    // Rebuild adjacent transitions safely to align with new sequence
    const newTransitions: TransitionConfig[] = [];
    for (let i = 0; i < updatedClips.length - 1; i++) {
      const c1 = updatedClips[i];
      const c2 = updatedClips[i + 1];
      const existing = (plan.transitions || []).find(t => t.from_clip_id === c1.id && t.to_clip_id === c2.id);
      if (existing) {
        newTransitions.push(existing);
      } else {
        newTransitions.push({
          id: `trans-${c1.id}-${c2.id}`,
          from_clip_id: c1.id,
          to_clip_id: c2.id,
          type: (c1.transition || 'none') as any,
          duration: 0.5,
          enabled: c1.transition !== 'none'
        });
      }
    }

    let acc = 0.0;
    const synced = updatedClips.map(c => {
      const s = Math.round(acc * 100) / 100;
      acc += c.duration;
      return { ...c, start_time: s };
    });

    onUpdatePlan({
      ...plan,
      duration_seconds: Math.round(acc * 100) / 100,
      clips: synced,
      transitions: newTransitions
    });

    setDraggedClipIndex(null);
    setDragOverIndex(null);
  };

  // Ruler click to seek
  const handleRulerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const targetTime = Math.max(0.0, Math.min(totalDuration, clickX / pxPerSec));
    onSeek(targetTime);
  };

  // Selected clip object for inspector
  const activeSelectedClip = clips.find(c => c.id === selectedClipId) || null;

  // Selected clip duration adjustment via buttons
  const handleAdjustDuration = (delta: number) => {
    if (!activeSelectedClip) return;
    const newDur = Math.max(0.5, Math.min(30.0, Math.round((activeSelectedClip.duration + delta) * 10) / 10));
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
    <footer className="h-52 border-t border-zinc-200 bg-white flex flex-col shrink-0 z-20 select-none">
      {/* 1. TIMELINE TOP BAR / INSPECTOR / ZOOM CONTROLS */}
      <div className="h-10 border-b border-zinc-200 px-4 flex items-center justify-between text-xs bg-zinc-50/80">
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
        className="flex-1 overflow-x-auto overflow-y-hidden relative bg-zinc-50/50"
      >
        <div
          style={{ width: `${timelineContentWidth}px` }}
          className="relative min-h-full flex flex-col p-2 space-y-1"
        >
          {/* PLAYHEAD NEEDLE */}
          <div
            style={{
              left: `${currentTime * pxPerSec + 24}px`, // +24px left track label offset
              transform: 'translateX(-50%)'
            }}
            className="absolute top-0 bottom-0 pointer-events-none z-40 flex flex-col items-center"
          >
            {/* Playhead badge */}
            <div className="w-3 h-3 bg-zinc-900 rotate-45 rounded-2xs shadow-xs" />
            <div className="w-0.5 flex-1 bg-zinc-900" />
          </div>

          {/* TIME RULER */}
          <div
            onClick={handleRulerClick}
            className="h-5 flex items-center relative cursor-pointer border-b border-zinc-200 pl-6"
            title="Click or drag on ruler to seek"
          >
            {rulerTicks.map(t => {
              const isSecond = Number.isInteger(t);
              const xPos = t * pxPerSec;
              return (
                <div
                  key={t}
                  style={{ left: `${xPos}px` }}
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
                  const isDraggingOver = dragOverIndex === i;
                  const leftPx = clip.start_time * pxPerSec;
                  const widthPx = Math.max(30, clip.duration * pxPerSec);

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
                          style={{ left: `${leftPx}px` }}
                          className="absolute top-0 bottom-0 w-1 bg-zinc-900 z-30 pointer-events-none rounded"
                        />
                      )}

                      {/* CLIP BLOCK */}
                      <div
                        draggable
                        onDragStart={e => handleDragStart(e, i)}
                        onDragOver={e => handleDragOver(e, i)}
                        onDrop={e => handleDrop(e, i)}
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
                          className="absolute right-0 top-0 bottom-0 w-2.5 cursor-ew-resize hover:bg-zinc-900/40 z-20 flex items-center justify-center group/handle"
                          title="Drag right edge to trim duration"
                        >
                          <div className="w-1 h-3 rounded-full bg-white/70 group-hover/handle:bg-white" />
                        </div>

                        {/* Thumbnail background */}
                        <img
                          src={getMediaUrl(clip.image_url)}
                          alt=""
                          className="w-full h-full object-cover pointer-events-none"
                        />

                        {/* Bottom clip duration badge */}
                        <div className="absolute inset-0 bg-gradient-to-t from-zinc-950/70 via-transparent to-transparent flex items-end justify-between p-1 text-[9px] font-mono text-white pointer-events-none">
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
                  {audioAnalysis ? `${audioAnalysis.tempo} BPM` : '120 BPM'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
};
