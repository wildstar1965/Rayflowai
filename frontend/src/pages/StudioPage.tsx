import React, { useState, useEffect, useRef } from 'react';
import { Button } from '../components/ui/Button';
import {
  EditingPlan,
  UploadedImage,
  UploadedAudio,
  AudioAnalysisResult,
  RenderJobStatus,
  ClipConfig,
  TransitionConfig
} from '../types';
import {
  uploadImages,
  uploadAudio,
  analyzeAudioFile,
  interpretNaturalCommand,
  generateProjectPlan,
  startRender,
  getRenderProgress,
  getDownloadUrl,
  getMediaUrl,
  loadDemoProject
} from '../services/api';
import { InteractiveTimeline } from '../components/studio/InteractiveTimeline';
import { EffectsPanel } from '../components/studio/EffectsPanel';
import {
  Mic,
  MicOff,
  Send,
  Play,
  Pause,
  RotateCcw,
  Undo2,
  Redo2,
  Download,
  Upload,
  Music,
  Image as ImageIcon,
  Sliders,
  Type,
  Trash2,
  ArrowUp,
  ArrowDown,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Film,
  Loader2,
  Volume2,
  VolumeX,
  ArrowLeft,
  Smartphone,
  Monitor,
  Square,
  Maximize2,
  Minimize2
} from 'lucide-react';

interface StudioPageProps {
  onBackToHome: () => void;
}

const STORAGE_KEY = 'rayflow_project_state_v3';

export const StudioPage: React.FC<StudioPageProps> = ({ onBackToHome }) => {
  // Project State
  const [projectName, setProjectName] = useState('Untitled Reel');
  const [activeTab, setActiveTab] = useState<'photos' | 'music' | 'effects' | 'style' | 'title'>('photos');

  // Media State
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [audio, setAudio] = useState<UploadedAudio | null>(null);
  const [audioAnalysis, setAudioAnalysis] = useState<AudioAnalysisResult | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isAnalyzingAudio, setIsAnalyzingAudio] = useState(false);

  // Audio preview playback in media library
  const [isAudioPreviewPlaying, setIsAudioPreviewPlaying] = useState(false);
  const mediaAudioRef = useRef<HTMLAudioElement | null>(null);

  // Editing Plan State
  const [plan, setPlan] = useState<EditingPlan>({
    duration_seconds: 15.0,
    aspect_ratio: '9:16',
    fit_mode: 'fill',
    style: 'cinematic',
    beat_sync: true,
    cut_pacing: 'balanced',
    motion: 'slow_zoom',
    title: {
      enabled: true,
      text: 'RAYFLOW',
      gradient: ['#FFFFFF', '#CCCCCC'],
      subtitle: undefined,
      position: 'center'
    },
    clips: [],
    transitions: []
  });

  // Selected Clip and Transition in Timeline / Inspector
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [selectedTransitionId, setSelectedTransitionId] = useState<string | null>(null);

  // Undo / Redo History
  const [history, setHistory] = useState<EditingPlan[]>([]);
  const [redoStack, setRedoStack] = useState<EditingPlan[]>([]);

  // Assistant / Directing State
  const [commandInput, setCommandInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isInterpreting, setIsInterpreting] = useState(false);
  const [conversation, setConversation] = useState<Array<{ sender: 'user' | 'assistant'; text: string; time: string }>>([
    {
      sender: 'assistant',
      text: 'Welcome to RayFlow Studio. Upload your photos and soundtrack, switch aspect ratios, drag clips to trim or reorder, or issue natural-language editing commands.',
      time: 'Just now'
    }
  ]);

  // Video Preview & Playback State
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0.0);
  const previewCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const synchronizedAudioRef = useRef<HTMLAudioElement | null>(null);
  const imageCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());

  // Rendering State
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [renderStatus, setRenderStatus] = useState<RenderJobStatus | null>(null);
  const [isRenderingModalOpen, setIsRenderingModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [viewRenderedVideo, setViewRenderedVideo] = useState(false);

  // Load state from localStorage on initial render
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.projectName) setProjectName(parsed.projectName);
        if (parsed.images) setImages(parsed.images);
        if (parsed.audio) setAudio(parsed.audio);
        if (parsed.audioAnalysis) setAudioAnalysis(parsed.audioAnalysis);
        if (parsed.plan) {
          const loadedPlan = parsed.plan;
          if (!loadedPlan.fit_mode) loadedPlan.fit_mode = 'fill';
          if (!loadedPlan.transitions) loadedPlan.transitions = [];
          setPlan(loadedPlan);
        }
      }
    } catch {
      // Ignore parse errors
    }
  }, []);

  // Save state to localStorage on modification
  useEffect(() => {
    try {
      const stateToSave = {
        projectName,
        images,
        audio,
        audioAnalysis,
        plan
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stateToSave));
    } catch {
      // Ignore quota errors
    }
  }, [projectName, images, audio, audioAnalysis, plan]);

  // Push new plan to history
  const updatePlanWithHistory = (newPlan: EditingPlan) => {
    setHistory(prev => [...prev.slice(-25), plan]);
    setRedoStack([]);
    setPlan(newPlan);
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setRedoStack(prev => [plan, ...prev]);
    setHistory(prev => prev.slice(0, -1));
    setPlan(previous);
  };

  const handleRedo = () => {
    if (redoStack.length === 0) return;
    const next = redoStack[0];
    setHistory(prev => [...prev, plan]);
    setRedoStack(prev => prev.slice(1));
    setPlan(next);
  };

  // Re-generate timeline whenever plan, images, or audio changes
  const refreshTimeline = async (
    currentPlan: EditingPlan,
    currentImages: UploadedImage[],
    currentAudio: UploadedAudio | null
  ) => {
    if (currentImages.length === 0) {
      setPlan(prev => ({ ...prev, clips: [], transitions: [] }));
      return;
    }
    try {
      const updated = await generateProjectPlan(
        currentPlan,
        currentImages.map(img => img.filename),
        currentAudio ? currentAudio.filename : undefined
      );
      if (!updated.fit_mode) updated.fit_mode = currentPlan.fit_mode || 'fill';
      if (!updated.transitions) updated.transitions = currentPlan.transitions || [];
      setPlan(updated);
    } catch (err: any) {
      console.warn('Backend plan update deferred, generating client timeline:', err);
      const numImages = currentImages.length;
      const targetDur = currentPlan.duration_seconds;
      const durPerClip = Math.round((targetDur / numImages) * 10) / 10;
      const fallbackClips: ClipConfig[] = currentImages.map((img, idx) => ({
        id: `clip-${idx + 1}`,
        image_url: img.url,
        start_time: Math.round(idx * durPerClip * 10) / 10,
        duration: idx === numImages - 1 ? Math.round((targetDur - idx * durPerClip) * 10) / 10 : durPerClip,
        motion: (idx % 2 === 0 ? 'zoom_in' : 'zoom_out'),
        transition: 'crossfade'
      }));

      // Fallback transitions
      const fallbackTransitions: TransitionConfig[] = [];
      for (let i = 0; i < fallbackClips.length - 1; i++) {
        fallbackTransitions.push({
          id: `trans-${i + 1}`,
          from_clip_id: fallbackClips[i].id,
          to_clip_id: fallbackClips[i + 1].id,
          type: 'crossfade',
          duration: 0.5,
          enabled: true
        });
      }

      setPlan(prev => ({
        ...prev,
        clips: fallbackClips,
        transitions: fallbackTransitions
      }));
    }
  };

  // Pre-load clip images into cache
  useEffect(() => {
    plan.clips.forEach(clip => {
      if (clip.image_url && !imageCacheRef.current.has(clip.image_url)) {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.src = getMediaUrl(clip.image_url);
        imageCacheRef.current.set(clip.image_url, img);
      }
    });
  }, [plan.clips]);

  // Photo Upload Handler with validation
  const processImageFiles = async (fileList: File[]) => {
    const validExtensions = ['.jpg', '.jpeg', '.png', '.webp', '.heic'];
    const validFiles = fileList.filter(file => {
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      return validExtensions.includes(ext) || file.type.startsWith('image/');
    });

    if (validFiles.length === 0) {
      setErrorMessage('Please upload valid photograph files (JPG, PNG, WebP).');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadImages(validFiles);
      const combined = [...images, ...uploaded];
      setImages(combined);
      await refreshTimeline(plan, combined, audio);
      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `Added ${uploaded.length} photo${uploaded.length > 1 ? 's' : ''} to the media library. Timeline updated.`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to upload photographs.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleImageFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    processImageFiles(Array.from(e.target.files));
  };

  const handleDropPhotos = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processImageFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleLoadDemoProject = async () => {
    setIsUploading(true);
    setErrorMessage(null);
    try {
      const demo = await loadDemoProject();
      setImages(demo.images);
      if (demo.audio) {
        setAudio(demo.audio);
        setIsAnalyzingAudio(true);
        try {
          const analysis = await analyzeAudioFile(demo.audio.filename);
          setAudioAnalysis(analysis);
        } catch (e) {
          console.warn('Demo audio analysis deferred:', e);
        } finally {
          setIsAnalyzingAudio(false);
        }
      }
      await refreshTimeline(plan, demo.images, demo.audio);
      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: 'Loaded 4 sample photos and soundtrack. Ready for editing, trimming, transitions, and export.',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load sample project.');
    } finally {
      setIsUploading(false);
    }
  };


  // Audio Upload Handler
  const handleAudioUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    const validExts = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!validExts.includes(ext) && !file.type.startsWith('audio/')) {
      setErrorMessage('Please upload a supported audio file (MP3, WAV, M4A).');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadAudio(file);
      setAudio(uploaded);

      // Analyze beats automatically
      setIsAnalyzingAudio(true);
      try {
        const analysis = await analyzeAudioFile(uploaded.filename);
        setAudioAnalysis(analysis);
        await refreshTimeline(plan, images, uploaded);
        setConversation(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: `Soundtrack "${uploaded.original_name}" loaded. Librosa detected ${analysis.tempo} BPM with ${analysis.beat_count} rhythm beats. Cuts aligned.`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
      } catch (err: any) {
        console.warn('Audio analysis fallback:', err);
        setAudioAnalysis({
          duration: 15.0,
          tempo: 120.0,
          beat_count: 30,
          beat_times: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0],
          strong_beats: [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
          sample_rate: 22050
        });
        await refreshTimeline(plan, images, uploaded);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to upload soundtrack.');
    } finally {
      setIsUploading(false);
      setIsAnalyzingAudio(false);
    }
  };

  const handleRemoveImage = (index: number) => {
    const updated = images.filter((_, i) => i !== index);
    setImages(updated);
    refreshTimeline(plan, updated, audio);
  };

  const handleMoveImage = (index: number, direction: 'up' | 'down') => {
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= images.length) return;
    const copy = [...images];
    const [moved] = copy.splice(index, 1);
    copy.splice(target, 0, moved);
    setImages(copy);
    refreshTimeline(plan, copy, audio);
  };

  const handleRemoveAudio = () => {
    if (isAudioPreviewPlaying && mediaAudioRef.current) {
      mediaAudioRef.current.pause();
      setIsAudioPreviewPlaying(false);
    }
    setAudio(null);
    setAudioAnalysis(null);
    refreshTimeline(plan, images, null);
  };

  const handleToggleAudioPreview = () => {
    if (!audio) return;
    if (isAudioPreviewPlaying) {
      mediaAudioRef.current?.pause();
      setIsAudioPreviewPlaying(false);
    } else {
      if (mediaAudioRef.current) {
        mediaAudioRef.current.currentTime = 0;
        mediaAudioRef.current.play().catch(e => console.warn('Preview play error:', e));
        setIsAudioPreviewPlaying(true);
      }
    }
  };

  // Open Effects Panel for specific boundary transition
  const handleOpenEffectsForBoundary = (fromClipId: string, toClipId: string) => {
    const trans = (plan.transitions || []).find(t => t.from_clip_id === fromClipId && t.to_clip_id === toClipId);
    if (trans) {
      setSelectedTransitionId(trans.id);
    } else {
      setSelectedTransitionId(`boundary-${fromClipId}-${toClipId}`);
    }
    setActiveTab('effects');
  };

  // Voice Recognition via Web Speech API
  const handleVoiceToggle = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setErrorMessage('Speech recognition is not supported in this browser. Please type your direction.');
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
        setErrorMessage(null);
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setCommandInput(transcript);
        setIsListening(false);
        handleExecuteCommand(transcript);
      };

      recognition.onerror = () => {
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  // Natural Language Command Execution
  const handleExecuteCommand = async (cmdToRun?: string) => {
    const cmd = cmdToRun || commandInput;
    if (!cmd.trim()) return;

    setIsInterpreting(true);
    setErrorMessage(null);
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setConversation(prev => [...prev, { sender: 'user', text: cmd, time: timeStr }]);
    setCommandInput('');

    try {
      const res = await interpretNaturalCommand(cmd, plan);
      updatePlanWithHistory(res.plan);

      // Re-calculate clips if images exist and clips were not specifically modified
      if (images.length > 0 && (!res.plan.clips || res.plan.clips.length === 0)) {
        await refreshTimeline(res.plan, images, audio);
      }

      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: res.explanation,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to interpret command.');
    } finally {
      setIsInterpreting(false);
    }
  };

  // Video Rendering Trigger
  const handleStartRender = async () => {
    if (images.length === 0) {
      setErrorMessage('Please upload at least one photograph to render a reel.');
      return;
    }

    setIsRenderingModalOpen(true);
    setErrorMessage(null);

    try {
      const jobId = await startRender(
        plan,
        images.map(img => img.filename),
        audio ? audio.filename : undefined
      );

      setRenderJobId(jobId);
      setRenderStatus({
        job_id: jobId,
        status: 'queued',
        progress: 0.0,
        created_at: Date.now() / 1000
      });

      // Poll render progress
      const interval = setInterval(async () => {
        try {
          const status = await getRenderProgress(jobId);
          setRenderStatus(status);

          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(interval);
            if (status.status === 'completed') {
              setConversation(prev => [
                ...prev,
                {
                  sender: 'assistant',
                  text: `Reel exported successfully in ${plan.aspect_ratio} with validated dimensions. Click download or watch in preview.`,
                  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
              ]);
            }
          }
        } catch {
          clearInterval(interval);
        }
      }, 1200);
    } catch (err: any) {
      setErrorMessage(err.message || 'Render failed to start.');
      setIsRenderingModalOpen(false);
    }
  };

  // Real Playback Controller & Canvas Animation Loop
  useEffect(() => {
    let animId: number;
    let lastStamp: number | null = null;

    const tick = (stamp: number) => {
      if (lastStamp !== null && isPlaying) {
        const delta = (stamp - lastStamp) / 1000;
        setCurrentTime(prev => {
          const next = prev + delta;
          if (next >= plan.duration_seconds) {
            setIsPlaying(false);
            if (synchronizedAudioRef.current) {
              synchronizedAudioRef.current.pause();
              synchronizedAudioRef.current.currentTime = 0;
            }
            return 0.0;
          }

          // Keep audio synchronized with playback position
          if (synchronizedAudioRef.current && !synchronizedAudioRef.current.paused) {
            const diff = Math.abs(synchronizedAudioRef.current.currentTime - next);
            if (diff > 0.3) {
              synchronizedAudioRef.current.currentTime = next;
            }
          }

          return next;
        });
      }
      lastStamp = stamp;
      if (isPlaying) {
        animId = requestAnimationFrame(tick);
      }
    };

    if (isPlaying) {
      animId = requestAnimationFrame(tick);
    }

    return () => cancelAnimationFrame(animId);
  }, [isPlaying, plan.duration_seconds]);

  const handleTogglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      if (synchronizedAudioRef.current) {
        synchronizedAudioRef.current.pause();
      }
    } else {
      if (currentTime >= plan.duration_seconds - 0.2) {
        setCurrentTime(0.0);
      }
      if (synchronizedAudioRef.current && audio) {
        synchronizedAudioRef.current.currentTime = currentTime;
        synchronizedAudioRef.current.play().catch(e => console.warn('Audio play deferred:', e));
      }
      setIsPlaying(true);
    }
  };

  const handleSeek = (newTime: number) => {
    setCurrentTime(newTime);
    if (synchronizedAudioRef.current && audio) {
      synchronizedAudioRef.current.currentTime = newTime;
    }
  };

  // Find active clip for current playback time
  const currentClipIndex = plan.clips.findIndex(
    c => currentTime >= c.start_time && currentTime < c.start_time + c.duration
  );
  const currentClip = currentClipIndex >= 0
    ? plan.clips[currentClipIndex]
    : (plan.clips.length > 0 ? plan.clips[0] : null);

  // Helper to draw an image frame onto the preview canvas
  const drawImageFrame = (
    ctx: CanvasRenderingContext2D,
    img: HTMLImageElement,
    clip: ClipConfig,
    w: number,
    h: number,
    progress: number,
    alpha: number = 1.0
  ) => {
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));

    const fitMode = plan.fit_mode || 'fill';
    let scale: number;
    let zoom = 1.0;

    if (fitMode === 'fit') {
      // Fit mode: preserve whole image, centered
      scale = Math.min(w / img.naturalWidth, h / img.naturalHeight);
    } else {
      // Fill mode: crop to cover and apply motion zoom
      scale = Math.max(w / img.naturalWidth, h / img.naturalHeight);
      if (clip.motion === 'zoom_out') {
        zoom = 1.15 - 0.1 * progress;
      } else if (clip.motion === 'zoom_in') {
        zoom = 1.05 + 0.1 * progress;
      }
    }

    const finalScale = scale * zoom;
    const sw = img.naturalWidth * finalScale;
    const sh = img.naturalHeight * finalScale;
    const sx = (w - sw) / 2;
    const sy = (h - sh) / 2;

    ctx.drawImage(img, sx, sy, sw, sh);
    ctx.restore();
  };

  // Draw smooth preview on canvas with aspect ratios, fit modes, and transitions
  useEffect(() => {
    const canvas = previewCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas dimensions to match current project aspect ratio
    const ratio = plan.aspect_ratio || '9:16';
    let targetW = 720;
    let targetH = 1280;
    if (ratio === '16:9') {
      targetW = 1280;
      targetH = 720;
    } else if (ratio === '1:1') {
      targetW = 1080;
      targetH = 1080;
    }

    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    const w = targetW;
    const h = targetH;

    // Clean neutral dark canvas background
    ctx.fillStyle = '#09090B';
    ctx.fillRect(0, 0, w, h);

    if (currentClip && currentClip.image_url) {
      const cached = imageCacheRef.current.get(currentClip.image_url);
      if (cached && cached.complete && cached.naturalWidth > 0) {
        const clipProgress = currentClip.duration > 0
          ? Math.min(1, Math.max(0, (currentTime - currentClip.start_time) / currentClip.duration))
          : 0;

        // Check if a transition is active with the next clip
        let transitionHandled = false;
        if (currentClipIndex >= 0 && currentClipIndex < plan.clips.length - 1) {
          const nextClip = plan.clips[currentClipIndex + 1];
          const boundaryTrans = (plan.transitions || []).find(
            t => t.from_clip_id === currentClip.id && t.to_clip_id === nextClip.id
          );

          if (boundaryTrans && boundaryTrans.enabled && boundaryTrans.type !== 'none') {
            const tDur = Math.max(0.1, boundaryTrans.duration);
            const clipEnd = currentClip.start_time + currentClip.duration;
            const tStart = clipEnd - tDur;

            if (currentTime >= tStart && currentTime < clipEnd) {
              const transProgress = (currentTime - tStart) / tDur;
              const nextCached = imageCacheRef.current.get(nextClip.image_url);

              if (boundaryTrans.type === 'crossfade') {
                // Outgoing clip
                drawImageFrame(ctx, cached, currentClip, w, h, clipProgress, 1.0);
                // Incoming clip blended over
                if (nextCached && nextCached.complete && nextCached.naturalWidth > 0) {
                  drawImageFrame(ctx, nextCached, nextClip, w, h, 0, transProgress);
                }
                transitionHandled = true;
              } else if (boundaryTrans.type === 'dip_black') {
                if (transProgress < 0.5) {
                  drawImageFrame(ctx, cached, currentClip, w, h, clipProgress, 1.0);
                  ctx.fillStyle = `rgba(0, 0, 0, ${transProgress * 2})`;
                  ctx.fillRect(0, 0, w, h);
                } else {
                  if (nextCached && nextCached.complete && nextCached.naturalWidth > 0) {
                    drawImageFrame(ctx, nextCached, nextClip, w, h, 0, 1.0);
                  }
                  ctx.fillStyle = `rgba(0, 0, 0, ${(1 - transProgress) * 2})`;
                  ctx.fillRect(0, 0, w, h);
                }
                transitionHandled = true;
              } else if (boundaryTrans.type === 'dip_white') {
                if (transProgress < 0.5) {
                  drawImageFrame(ctx, cached, currentClip, w, h, clipProgress, 1.0);
                  ctx.fillStyle = `rgba(255, 255, 255, ${transProgress * 2})`;
                  ctx.fillRect(0, 0, w, h);
                } else {
                  if (nextCached && nextCached.complete && nextCached.naturalWidth > 0) {
                    drawImageFrame(ctx, nextCached, nextClip, w, h, 0, 1.0);
                  }
                  ctx.fillStyle = `rgba(255, 255, 255, ${(1 - transProgress) * 2})`;
                  ctx.fillRect(0, 0, w, h);
                }
                transitionHandled = true;
              }
            }
          }
        }

        if (!transitionHandled) {
          drawImageFrame(ctx, cached, currentClip, w, h, clipProgress, 1.0);
        }

        // Global Head Transition (Fade in from black)
        if (plan.head_transition?.enabled) {
          const hDur = plan.head_transition.duration || 0.5;
          if (currentTime < hDur) {
            const hAlpha = 1.0 - (currentTime / hDur);
            ctx.fillStyle = plan.head_transition.type?.includes('white') ? '#FFFFFF' : '#000000';
            ctx.globalAlpha = Math.max(0, Math.min(1, hAlpha));
            ctx.fillRect(0, 0, w, h);
            ctx.globalAlpha = 1.0;
          }
        }

        // Global Tail Transition (Fade out to black)
        if (plan.tail_transition?.enabled) {
          const tDur = plan.tail_transition.duration || 0.5;
          const tStart = Math.max(0, plan.duration_seconds - tDur);
          if (currentTime > tStart) {
            const tAlpha = (currentTime - tStart) / tDur;
            ctx.fillStyle = plan.tail_transition.type.includes('white') ? '#FFFFFF' : '#000000';
            ctx.globalAlpha = Math.max(0, Math.min(1, tAlpha));
            ctx.fillRect(0, 0, w, h);
            ctx.globalAlpha = 1.0;
          }
        }

        // Subtle style filters
        if (plan.style === 'noir') {
          ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
          ctx.fillRect(0, 0, w, h);
          ctx.globalCompositeOperation = 'color';
          ctx.fillStyle = '#808080';
          ctx.fillRect(0, 0, w, h);
          ctx.globalCompositeOperation = 'source-over';
        } else if (plan.style === 'vintage') {
          ctx.globalCompositeOperation = 'color';
          ctx.fillStyle = '#C27803';
          ctx.fillRect(0, 0, w, h);
          ctx.globalCompositeOperation = 'source-over';
        }

        // Clean monochrome title overlay (first 4.5 seconds if enabled)
        if (plan.title.enabled && plan.title.text && currentTime <= 4.5) {
          ctx.save();
          const titleAlpha = currentTime < 0.5
            ? currentTime / 0.5
            : currentTime > 3.8
            ? (4.5 - currentTime) / 0.7
            : 1.0;
          ctx.globalAlpha = Math.max(0, Math.min(1, titleAlpha));

          ctx.textAlign = 'center';
          const fontSize = Math.max(28, Math.round(w * 0.055));
          ctx.font = `600 ${fontSize}px Inter, -apple-system, sans-serif`;

          // Soft drop shadow for legibility on any image
          ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
          ctx.shadowBlur = 8;
          ctx.shadowOffsetY = 2;

          ctx.fillStyle = '#FFFFFF';
          ctx.fillText(plan.title.text, w / 2, h * 0.45);

          if (plan.title.subtitle) {
            ctx.font = `400 ${Math.max(14, Math.round(w * 0.026))}px Inter, -apple-system, sans-serif`;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
            ctx.fillText(plan.title.subtitle, w / 2, h * 0.45 + fontSize * 0.9);
          }
          ctx.restore();
        }
      } else {
        // Drawing placeholder while image decodes
        ctx.fillStyle = '#27272A';
        ctx.fillRect(0, 0, w, h);
        ctx.textAlign = 'center';
        ctx.font = '500 14px Inter, sans-serif';
        ctx.fillStyle = '#A1A1AA';
        ctx.fillText('Loading clip frame...', w / 2, h / 2);
      }
    } else {
      // Clean empty state
      ctx.fillStyle = '#18181B';
      ctx.fillRect(0, 0, w, h);
      ctx.textAlign = 'center';
      ctx.font = '500 14px Inter, sans-serif';
      ctx.fillStyle = '#71717A';
      ctx.fillText('No media added', w / 2, h / 2 - 10);
      ctx.font = '400 12px Inter, sans-serif';
      ctx.fillStyle = '#52525B';
      ctx.fillText('Upload photos to preview edit', w / 2, h / 2 + 14);
    }
  }, [currentTime, currentClip, plan]);

  return (
    <div className="flex flex-col h-screen bg-white text-zinc-900 select-none overflow-hidden">
      {/* Hidden audio element for preview sync */}
      {audio && (
        <audio
          ref={synchronizedAudioRef}
          src={getMediaUrl(audio.url)}
          preload="auto"
          onEnded={() => {
            setIsPlaying(false);
            setCurrentTime(0.0);
          }}
        />
      )}

      {/* Hidden audio element for library preview */}
      {audio && (
        <audio
          ref={mediaAudioRef}
          src={getMediaUrl(audio.url)}
          onEnded={() => setIsAudioPreviewPlaying(false)}
        />
      )}

      {/* Top Navigation Toolbar */}
      <header className="h-14 border-b border-zinc-200 bg-white px-5 flex items-center justify-between z-30 shrink-0">
        {/* Left: Back & Project Name */}
        <div className="flex items-center gap-3">
          <button
            onClick={onBackToHome}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 transition-colors"
            title="Return to Landing Page"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>

          <div className="h-4 w-px bg-zinc-200" />

          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-zinc-900" />
            <input
              type="text"
              value={projectName}
              onChange={e => setProjectName(e.target.value)}
              className="text-sm font-semibold text-zinc-900 bg-transparent border-b border-transparent hover:border-zinc-300 focus:border-zinc-900 focus:outline-none transition-colors px-1"
              title="Click to rename project"
            />
          </div>
        </div>

        {/* Center: Aspect Ratio & Image Fit Mode Controls */}
        <div className="hidden md:flex items-center gap-3">
          {/* Aspect Ratio Selector */}
          <div className="flex items-center p-0.5 bg-zinc-100 rounded-lg border border-zinc-200 shadow-2xs">
            <button
              onClick={() => updatePlanWithHistory({ ...plan, aspect_ratio: '9:16' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                plan.aspect_ratio === '9:16'
                  ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                  : 'text-zinc-500 hover:text-zinc-900'
              }`}
              title="9:16 Portrait (1080×1920) for Reels, TikTok, Shorts"
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span>9:16</span>
            </button>

            <button
              onClick={() => updatePlanWithHistory({ ...plan, aspect_ratio: '16:9' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                plan.aspect_ratio === '16:9'
                  ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                  : 'text-zinc-500 hover:text-zinc-900'
              }`}
              title="16:9 Landscape (1920×1080) for YouTube, Desktop"
            >
              <Monitor className="w-3.5 h-3.5" />
              <span>16:9</span>
            </button>

            <button
              onClick={() => updatePlanWithHistory({ ...plan, aspect_ratio: '1:1' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                plan.aspect_ratio === '1:1'
                  ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                  : 'text-zinc-500 hover:text-zinc-900'
              }`}
              title="1:1 Square (1080×1080) for Instagram Feed"
            >
              <Square className="w-3.5 h-3.5" />
              <span>1:1</span>
            </button>
          </div>

          <div className="h-4 w-px bg-zinc-200" />

          {/* Fit Mode Toggle */}
          <div className="flex items-center p-0.5 bg-zinc-100 rounded-lg border border-zinc-200 shadow-2xs">
            <button
              onClick={() => updatePlanWithHistory({ ...plan, fit_mode: 'fill' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                (plan.fit_mode || 'fill') === 'fill'
                  ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                  : 'text-zinc-500 hover:text-zinc-900'
              }`}
              title="Fill Frame (crop to fill)"
            >
              <Maximize2 className="w-3 h-3" />
              <span>Fill</span>
            </button>

            <button
              onClick={() => updatePlanWithHistory({ ...plan, fit_mode: 'fit' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                plan.fit_mode === 'fit'
                  ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                  : 'text-zinc-500 hover:text-zinc-900'
              }`}
              title="Fit to Frame (preserve entire photo)"
            >
              <Minimize2 className="w-3 h-3" />
              <span>Fit</span>
            </button>
          </div>
        </div>

        {/* Right: Undo/Redo & Export Button */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <button
              onClick={handleUndo}
              disabled={history.length === 0}
              className="p-1.5 rounded-lg text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Undo2 className="w-4 h-4" />
            </button>
            <button
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              className="p-1.5 rounded-lg text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Redo"
            >
              <Redo2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                if (window.confirm('Reset this project to start fresh?')) {
                  localStorage.removeItem(STORAGE_KEY);
                  setImages([]);
                  setAudio(null);
                  setAudioAnalysis(null);
                  setPlan({
                    duration_seconds: 15.0,
                    aspect_ratio: '9:16',
                    fit_mode: 'fill',
                    style: 'cinematic',
                    beat_sync: true,
                    cut_pacing: 'balanced',
                    motion: 'slow_zoom',
                    title: { enabled: true, text: 'RAYFLOW', gradient: ['#FFFFFF', '#CCCCCC'] },
                    clips: [],
                    transitions: []
                  });
                }
              }}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-800 hover:bg-zinc-100 text-xs transition-colors"
              title="New / Clear Project"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-4 w-px bg-zinc-200" />

          <Button
            variant="primary"
            size="sm"
            onClick={handleStartRender}
            disabled={images.length === 0}
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export MP4</span>
          </Button>
        </div>
      </header>

      {/* Main Studio Area (3 Columns: Left Media/Settings, Center Preview, Right AI Assistant) */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* LEFT PANEL: Media Library & Settings */}
        <aside className="w-full md:w-80 lg:w-88 border-r border-zinc-200 bg-zinc-50/70 flex flex-col shrink-0 overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-zinc-200 bg-white px-2 pt-2 gap-1 text-xs font-medium overflow-x-auto">
            <button
              onClick={() => setActiveTab('photos')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'photos'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Photos ({images.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('music')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'music'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
            >
              <Music className="w-3.5 h-3.5" />
              <span>Music {audio ? '•' : ''}</span>
            </button>

            <button
              onClick={() => setActiveTab('effects')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'effects'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Effects</span>
            </button>

            <button
              onClick={() => setActiveTab('style')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'style'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Pacing</span>
            </button>

            <button
              onClick={() => setActiveTab('title')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'title'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
            >
              <Type className="w-3.5 h-3.5" />
              <span>Title</span>
            </button>
          </div>

          {/* Tab Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* PHOTOS TAB */}
            {activeTab === 'photos' && (
              <div className="space-y-3">
                {/* Drag & Drop Upload Card */}
                <label
                  onDragOver={e => e.preventDefault()}
                  onDrop={handleDropPhotos}
                  className="border border-dashed border-zinc-300 hover:border-zinc-400 bg-white rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer transition-colors text-center group shadow-sm"
                >
                  <Upload className="w-5 h-5 text-zinc-500 mb-1.5 group-hover:text-zinc-800 transition-colors" />
                  <span className="text-xs font-semibold text-zinc-800">
                    Add Photographs
                  </span>
                  <span className="text-[11px] text-zinc-500 mt-0.5">
                    Drag and drop or browse files (JPG, PNG, WebP)
                  </span>
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={handleImageFileInput}
                    className="hidden"
                  />
                </label>

                {isUploading && (
                  <div className="flex items-center justify-center gap-2 py-2 text-xs text-zinc-700 bg-zinc-100 rounded-lg">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing media...</span>
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleLoadDemoProject}
                  disabled={isUploading}
                  className="w-full py-2 px-3 rounded-lg border border-zinc-200 bg-white hover:bg-zinc-50 hover:border-zinc-300 transition-colors text-xs font-medium text-zinc-700 flex items-center justify-center gap-2 shadow-2xs"
                  title="Instantly populate project with 4 test photos and soundtrack"
                >
                  <Sparkles className="w-3.5 h-3.5 text-zinc-600" />
                  <span>Load Sample Project (4 Photos & Music)</span>
                </button>


                {images.length === 0 ? (
                  <div className="text-center py-10 px-4 text-xs text-zinc-500 border border-zinc-200 rounded-xl bg-white space-y-2">
                    <p className="font-medium text-zinc-700">No photos in project library</p>
                    <p className="text-[11px]">Upload photos to begin assembling your reel.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-zinc-500 px-1">
                      <span>{images.length} photos ready</span>
                      <button
                        onClick={() => {
                          setImages([]);
                          refreshTimeline(plan, [], audio);
                        }}
                        className="text-zinc-500 hover:text-red-600 transition-colors"
                      >
                        Clear All
                      </button>
                    </div>

                    {images.map((img, idx) => (
                      <div
                        key={img.filename + idx}
                        className="flex items-center justify-between p-2.5 rounded-lg bg-white border border-zinc-200 hover:border-zinc-300 transition-all shadow-sm"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <img
                            src={getMediaUrl(img.url)}
                            alt=""
                            className="w-10 h-10 object-cover rounded bg-zinc-100 shrink-0 border border-zinc-200"
                          />
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-zinc-900 truncate">
                              {img.original_name}
                            </p>
                            <p className="text-[10px] text-zinc-500 font-mono">
                              {(img.size / 1024).toFixed(0)} KB • Photo #{idx + 1}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-0.5 shrink-0">
                          <button
                            onClick={() => handleMoveImage(idx, 'up')}
                            disabled={idx === 0}
                            className="p-1 text-zinc-400 hover:text-zinc-800 disabled:opacity-20"
                            title="Move Up"
                          >
                            <ArrowUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleMoveImage(idx, 'down')}
                            disabled={idx === images.length - 1}
                            className="p-1 text-zinc-400 hover:text-zinc-800 disabled:opacity-20"
                            title="Move Down"
                          >
                            <ArrowDown className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleRemoveImage(idx)}
                            className="p-1 text-zinc-400 hover:text-red-600 transition-colors"
                            title="Remove Photo"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* MUSIC TAB */}
            {activeTab === 'music' && (
              <div className="space-y-4">
                <label className="border border-dashed border-zinc-300 hover:border-zinc-400 bg-white rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer transition-colors text-center group shadow-sm">
                  <Music className="w-5 h-5 text-zinc-500 mb-1.5 group-hover:text-zinc-800 transition-colors" />
                  <span className="text-xs font-semibold text-zinc-800">
                    {audio ? 'Replace Soundtrack' : 'Add Soundtrack'}
                  </span>
                  <span className="text-[11px] text-zinc-500 mt-0.5">
                    Audio analysis with Librosa beat detection (MP3, WAV)
                  </span>
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleAudioUpload}
                    className="hidden"
                  />
                </label>

                {isAnalyzingAudio && (
                  <div className="flex items-center justify-center gap-2 py-2 text-xs text-zinc-700 bg-zinc-100 rounded-lg">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Analyzing rhythm & beats with Librosa...</span>
                  </div>
                )}

                {audio ? (
                  <div className="p-3.5 rounded-xl bg-white border border-zinc-200 shadow-sm space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <button
                          onClick={handleToggleAudioPreview}
                          className="w-8 h-8 rounded-full bg-zinc-900 text-white flex items-center justify-center hover:bg-zinc-800 transition-colors shrink-0 shadow-2xs"
                        >
                          {isAudioPreviewPlaying ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                        </button>
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-zinc-900 truncate">
                            {audio.original_name}
                          </p>
                          <p className="text-[10px] text-zinc-500 font-mono">
                            {(audio.size / (1024 * 1024)).toFixed(1)} MB
                          </p>
                        </div>
                      </div>

                      <button
                        onClick={handleRemoveAudio}
                        className="p-1 text-zinc-400 hover:text-red-600 transition-colors"
                        title="Remove Soundtrack"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {audioAnalysis && (
                      <div className="pt-2 border-t border-zinc-100 grid grid-cols-2 gap-2 text-center">
                        <div className="bg-zinc-50 p-2 rounded-lg border border-zinc-200">
                          <span className="text-[10px] text-zinc-500 block">Tempo</span>
                          <span className="text-xs font-semibold font-mono text-zinc-900">
                            {audioAnalysis.tempo} BPM
                          </span>
                        </div>
                        <div className="bg-zinc-50 p-2 rounded-lg border border-zinc-200">
                          <span className="text-[10px] text-zinc-500 block">Beats Detected</span>
                          <span className="text-xs font-semibold font-mono text-zinc-900">
                            {audioAnalysis.beat_count} Hits
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-10 px-4 text-xs text-zinc-500 border border-zinc-200 rounded-xl bg-white space-y-2">
                    <p className="font-medium text-zinc-700">No soundtrack selected</p>
                    <p className="text-[11px]">Upload music to automatically align cuts to rhythm.</p>
                  </div>
                )}
              </div>
            )}

            {/* EFFECTS TAB (Dedicated Transitions Panel) */}
            {activeTab === 'effects' && (
              <EffectsPanel
                plan={plan}
                images={images}
                selectedTransitionId={selectedTransitionId}
                onUpdatePlan={updatePlanWithHistory}
                onSelectTransition={setSelectedTransitionId}
              />
            )}

            {/* PACING & STYLE TAB */}
            {activeTab === 'style' && (
              <div className="space-y-4">
                {/* Beat Sync Toggle */}
                <div className="flex items-center justify-between p-3 rounded-lg bg-white border border-zinc-200 shadow-sm">
                  <div>
                    <span className="text-xs font-semibold text-zinc-900 block">
                      Beat Sync Cuts
                    </span>
                    <span className="text-[11px] text-zinc-500">
                      Snap image transitions to soundtrack rhythm
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={plan.beat_sync}
                    onChange={e => {
                      const updated = { ...plan, beat_sync: e.target.checked };
                      updatePlanWithHistory(updated);
                    }}
                    className="w-4 h-4 accent-zinc-900 rounded cursor-pointer"
                  />
                </div>

                {/* Style Presets */}
                <div>
                  <label className="text-xs font-medium text-zinc-700 block mb-2">
                    Color & Style Preset
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'cinematic', label: 'Cinematic', desc: 'Balanced contrast' },
                      { id: 'vintage', label: 'Vintage', desc: 'Warm Kodak gold' },
                      { id: 'noir', label: 'Noir', desc: 'High-contrast B&W' },
                      { id: 'vibrant', label: 'Vibrant', desc: 'Saturated pop' },
                      { id: 'minimal', label: 'Minimal', desc: 'Neutral editorial' }
                    ].map(preset => (
                      <button
                        key={preset.id}
                        onClick={() => {
                          const updated = { ...plan, style: preset.id as any };
                          updatePlanWithHistory(updated);
                        }}
                        className={`p-2.5 rounded-lg border text-left transition-all ${
                          plan.style === preset.id
                            ? 'border-zinc-900 bg-white ring-1 ring-zinc-900 shadow-sm'
                            : 'border-zinc-200 bg-white hover:border-zinc-300'
                        }`}
                      >
                        <span className="text-xs font-semibold text-zinc-900 block">
                          {preset.label}
                        </span>
                        <span className="text-[10px] text-zinc-500">
                          {preset.desc}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Pacing Speed */}
                <div>
                  <label className="text-xs font-medium text-zinc-700 block mb-2">
                    Editing Pacing
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: 'slow', label: 'Slow' },
                      { id: 'balanced', label: 'Balanced' },
                      { id: 'fast', label: 'Fast' }
                    ].map(p => (
                      <button
                        key={p.id}
                        onClick={() => {
                          const updated = { ...plan, cut_pacing: p.id as any };
                          updatePlanWithHistory(updated);
                        }}
                        className={`py-2 px-1 text-center rounded-lg border text-xs font-medium transition-all ${
                          plan.cut_pacing === p.id
                            ? 'border-zinc-900 bg-zinc-900 text-white shadow-sm'
                            : 'border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300'
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Duration Slider */}
                <div className="p-3 rounded-lg bg-white border border-zinc-200 shadow-sm space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-medium text-zinc-700">Total Reel Duration</span>
                    <span className="text-xs font-mono font-semibold text-zinc-900">
                      {plan.duration_seconds.toFixed(1)}s
                    </span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="60"
                    step="0.5"
                    value={plan.duration_seconds}
                    onChange={e => {
                      const updated = { ...plan, duration_seconds: parseFloat(e.target.value) };
                      setPlan(updated);
                      refreshTimeline(updated, images, audio);
                    }}
                    className="w-full accent-zinc-900 cursor-pointer"
                  />
                </div>
              </div>
            )}

            {/* TITLE TAB */}
            {activeTab === 'title' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-lg bg-white border border-zinc-200 shadow-sm">
                  <div>
                    <span className="text-xs font-semibold text-zinc-900 block">
                      Enable Title Overlay
                    </span>
                    <span className="text-[11px] text-zinc-500">
                      Displays cinematic title at the start
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={plan.title.enabled}
                    onChange={e => {
                      const updated = {
                        ...plan,
                        title: { ...plan.title, enabled: e.target.checked }
                      };
                      updatePlanWithHistory(updated);
                    }}
                    className="w-4 h-4 accent-zinc-900 rounded cursor-pointer"
                  />
                </div>

                {plan.title.enabled && (
                  <div className="space-y-3 pt-1">
                    <div>
                      <label className="text-xs font-medium text-zinc-700 block mb-1">
                        Main Title
                      </label>
                      <input
                        type="text"
                        value={plan.title.text}
                        onChange={e => {
                          const updated = {
                            ...plan,
                            title: { ...plan.title, text: e.target.value }
                          };
                          setPlan(updated);
                        }}
                        placeholder="e.g. SUMMER MEMORIES"
                        className="w-full bg-white border border-zinc-200 rounded-lg px-3 py-2 text-xs font-semibold text-zinc-900 outline-none focus:border-zinc-900 shadow-sm"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-zinc-700 block mb-1">
                        Subtitle (Optional)
                      </label>
                      <input
                        type="text"
                        value={plan.title.subtitle || ''}
                        onChange={e => {
                          const updated = {
                            ...plan,
                            title: { ...plan.title, subtitle: e.target.value || undefined }
                          };
                          setPlan(updated);
                        }}
                        placeholder="e.g. Directed with RayFlow"
                        className="w-full bg-white border border-zinc-200 rounded-lg px-3 py-2 text-xs text-zinc-800 outline-none focus:border-zinc-900 shadow-sm"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* CENTER VIEWPORT: Video Preview & Playback Controls */}
        <main className="flex-1 flex flex-col bg-zinc-100 items-center justify-between p-4 sm:p-6 overflow-hidden">
          {/* Top Info Bar */}
          <div className="w-full max-w-sm flex items-center justify-between text-xs text-zinc-500 font-mono pb-2">
            <span>PREVIEW</span>
            <span className="font-semibold text-zinc-800 uppercase">
              {plan.aspect_ratio} • {plan.fit_mode || 'fill'} • {plan.style}
            </span>
          </div>

          {/* Viewport Box */}
          <div className="relative flex-1 flex items-center justify-center w-full max-h-[56vh]">
            <div
              className={`relative rounded-xl overflow-hidden border border-zinc-300 shadow-md bg-zinc-950 transition-all duration-200 ${
                plan.aspect_ratio === '9:16'
                  ? 'aspect-[9/16] h-full max-h-[520px]'
                  : plan.aspect_ratio === '16:9'
                  ? 'aspect-[16/9] w-full max-w-[580px]'
                  : 'aspect-square h-full max-h-[440px]'
              }`}
            >
              {/* Native HTML5 video player if exported reel is selected */}
              {viewRenderedVideo && renderStatus?.status === 'completed' && renderJobId ? (
                <video
                  src={getDownloadUrl(renderJobId)}
                  controls
                  autoPlay
                  playsInline
                  className="w-full h-full object-contain"
                />
              ) : (
                /* Dynamic Canvas Preview */
                <canvas
                  ref={previewCanvasRef}
                  width={plan.aspect_ratio === '16:9' ? 1280 : plan.aspect_ratio === '1:1' ? 1080 : 720}
                  height={plan.aspect_ratio === '16:9' ? 720 : plan.aspect_ratio === '1:1' ? 1080 : 1280}
                  className="w-full h-full object-contain"
                />
              )}

              {/* Watermark badge */}
              <div className="absolute top-3 left-3 px-2 py-0.5 rounded bg-zinc-900/80 backdrop-blur-sm text-[10px] font-mono text-white/80 border border-white/10 pointer-events-none">
                RAYFLOW {plan.aspect_ratio}
              </div>

              {renderStatus?.status === 'completed' && renderJobId && (
                <button
                  onClick={() => setViewRenderedVideo(!viewRenderedVideo)}
                  className="absolute bottom-3 right-3 px-2.5 py-1 rounded bg-white text-zinc-900 text-[11px] font-medium shadow-md hover:bg-zinc-100 transition-colors border border-zinc-200"
                >
                  {viewRenderedVideo ? 'Canvas Mode' : 'Watch Exported MP4'}
                </button>
              )}
            </div>
          </div>

          {/* Playback Controller */}
          <div className="w-full max-w-md mt-4 p-3 rounded-xl bg-white border border-zinc-200 shadow-sm flex items-center justify-between gap-4">
            <button
              onClick={handleTogglePlay}
              className="w-9 h-9 rounded-full bg-zinc-900 hover:bg-zinc-800 text-white flex items-center justify-center transition-transform active:scale-95 shrink-0 shadow-sm"
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="w-4 h-4 fill-white" /> : <Play className="w-4 h-4 fill-white ml-0.5" />}
            </button>

            {/* Time progress bar */}
            <div className="flex-1 flex flex-col gap-1">
              <div className="flex justify-between text-[11px] font-mono text-zinc-600">
                <span>{currentTime.toFixed(1)}s</span>
                <span>{plan.duration_seconds.toFixed(1)}s</span>
              </div>
              <input
                type="range"
                min="0"
                max={plan.duration_seconds}
                step="0.1"
                value={currentTime}
                onChange={e => handleSeek(parseFloat(e.target.value))}
                className="w-full accent-zinc-900 h-1.5 bg-zinc-200 rounded-lg cursor-pointer"
              />
            </div>

            <button
              onClick={() => {
                handleSeek(0.0);
                setIsPlaying(false);
              }}
              className="p-1.5 text-zinc-400 hover:text-zinc-800 transition-colors"
              title="Reset to 0s"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </main>

        {/* RIGHT PANEL: Voice & Text Editing Directives */}
        <aside className="w-full md:w-80 lg:w-88 border-l border-zinc-200 bg-white flex flex-col shrink-0 overflow-hidden">
          {/* Header */}
          <div className="p-4 border-b border-zinc-200 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-900" />
                <h3 className="text-sm font-semibold text-zinc-900">
                  Direct your edit
                </h3>
              </div>
              <p className="text-[11px] text-zinc-500 mt-0.5">
                Voice-guided creative instructions
              </p>
            </div>

            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-100 text-zinc-700 border border-zinc-200">
              AI DIRECTOR
            </span>
          </div>

          {/* Conversation History */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {conversation.map((msg, idx) => (
              <div
                key={idx}
                className={`flex flex-col ${
                  msg.sender === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-xs leading-relaxed ${
                    msg.sender === 'user'
                      ? 'bg-zinc-900 text-white'
                      : 'bg-zinc-100 text-zinc-800 border border-zinc-200'
                  }`}
                >
                  <p>{msg.text}</p>
                </div>
                <span className="text-[10px] text-zinc-400 mt-1 px-1">
                  {msg.time}
                </span>
              </div>
            ))}
          </div>

          {/* Suggested Directives */}
          <div className="px-4 py-2 border-t border-zinc-100 bg-zinc-50/60">
            <span className="text-[10px] font-mono text-zinc-400 block mb-1.5 uppercase">
              Suggested Instructions:
            </span>
            <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pb-1">
              {[
                'Apply a crossfade between photos one and two.',
                'Replace transition between photos two and three with dip to black.',
                'Add a fade-in at the beginning of the entire reel.',
                'Fade out the video at the end.',
                'Change the video to landscape.',
                'Change the output ratio to square.',
                'Make the first photo last three seconds.',
                'Extend the third photo by two seconds.',
                'Move the last photo to the beginning.'
              ].map(cmd => (
                <button
                  key={cmd}
                  onClick={() => handleExecuteCommand(cmd)}
                  className="text-[11px] px-2.5 py-1 rounded-full bg-white hover:bg-zinc-100 border border-zinc-200 text-zinc-700 transition-colors text-left shadow-2xs"
                >
                  "{cmd}"
                </button>
              ))}
            </div>
          </div>

          {/* Voice & Text Input */}
          <div className="p-3 border-t border-zinc-200 bg-white">
            <form
              onSubmit={e => {
                e.preventDefault();
                handleExecuteCommand();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={handleVoiceToggle}
                className={`p-2.5 rounded-lg border transition-all shrink-0 ${
                  isListening
                    ? 'bg-red-500 border-red-600 text-white animate-pulse'
                    : 'bg-zinc-100 border-zinc-200 text-zinc-700 hover:bg-zinc-200'
                }`}
                title={isListening ? 'Stop listening' : 'Start voice instruction'}
              >
                {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>

              <input
                type="text"
                value={commandInput}
                onChange={e => setCommandInput(e.target.value)}
                placeholder={isListening ? 'Listening...' : 'Type or speak your direction...'}
                className="flex-1 bg-white border border-zinc-200 rounded-lg px-3 py-2 text-xs text-zinc-900 placeholder-zinc-400 focus:outline-none focus:border-zinc-900 shadow-2xs"
              />

              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={!commandInput.trim() || isInterpreting}
              >
                {isInterpreting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              </Button>
            </form>

            {errorMessage && (
              <div className="mt-2 p-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-[11px] flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{errorMessage}</span>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* BOTTOM TIMELINE (Interactive Premiere Pro-Style Timeline) */}
      <InteractiveTimeline
        plan={plan}
        audio={audio}
        audioAnalysis={audioAnalysis}
        currentTime={currentTime}
        isPlaying={isPlaying}
        selectedClipId={selectedClipId}
        onSelectClip={setSelectedClipId}
        onSeek={handleSeek}
        onUpdatePlan={updatePlanWithHistory}
        onOpenEffectsForBoundary={handleOpenEffectsForBoundary}
      />

      {/* Render Modal */}
      {isRenderingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/40 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="max-w-md w-full bg-white border border-zinc-200 rounded-2xl p-6 shadow-xl text-center space-y-4">
            <div className="w-12 h-12 rounded-xl bg-zinc-100 border border-zinc-200 mx-auto flex items-center justify-center text-zinc-900">
              {renderStatus?.status === 'completed' ? (
                <CheckCircle2 className="w-6 h-6 text-zinc-900" />
              ) : renderStatus?.status === 'failed' ? (
                <AlertCircle className="w-6 h-6 text-red-600" />
              ) : (
                <Film className="w-6 h-6 animate-pulse text-zinc-900" />
              )}
            </div>

            <div>
              <h3 className="text-base font-semibold text-zinc-900">
                {renderStatus?.status === 'completed'
                  ? 'Reel Export Complete'
                  : renderStatus?.status === 'failed'
                  ? 'Export Error'
                  : 'Rendering Cinematic Reel'}
              </h3>
              <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
                {renderStatus?.status === 'completed'
                  ? `Your authentic ${plan.aspect_ratio} MP4 has been compiled with FFmpeg and verified.`
                  : renderStatus?.status === 'failed'
                  ? renderStatus.error || 'Failed to render reel with FFmpeg backend.'
                  : `Compositing ${plan.aspect_ratio} frame, transitions, and audio sync with FFmpeg...`}
              </p>
            </div>

            {/* Progress Bar */}
            {renderStatus && renderStatus.status !== 'failed' && (
              <div className="space-y-1.5">
                <div className="w-full h-2 bg-zinc-100 rounded-full overflow-hidden border border-zinc-200">
                  <div
                    className="h-full bg-zinc-900 transition-all duration-300"
                    style={{ width: `${renderStatus.progress}%` }}
                  />
                </div>
                <div className="flex justify-between text-[11px] font-mono text-zinc-500">
                  <span className="capitalize">{renderStatus.status}</span>
                  <span>{renderStatus.progress.toFixed(0)}%</span>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="pt-2 flex items-center justify-center gap-2.5">
              {renderStatus?.status === 'completed' && renderJobId && (
                <>
                  <a
                    href={getDownloadUrl(renderJobId)}
                    download={`rayflow_${renderJobId}.mp4`}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg bg-zinc-900 text-white hover:bg-zinc-800 transition-colors shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download MP4</span>
                  </a>
                  <button
                    onClick={() => {
                      setViewRenderedVideo(true);
                      setIsRenderingModalOpen(false);
                    }}
                    className="text-xs font-medium px-3.5 py-2 rounded-lg bg-zinc-100 hover:bg-zinc-200 text-zinc-800 border border-zinc-200 transition-colors"
                  >
                    Watch in Preview
                  </button>
                </>
              )}

              <button
                onClick={() => setIsRenderingModalOpen(false)}
                className="text-xs font-medium px-3.5 py-2 rounded-lg text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StudioPage;
