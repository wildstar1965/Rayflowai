import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { Button } from '../components/ui/Button';
import {
  EditingPlan,
  UploadedImage,
  UploadedAudio,
  AudioAnalysisResult,
  RenderJobStatus,
  ClipConfig,
  SubtitleSegment,
  SubtitlePreset
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
  loadDemoProject,
  startTranscription,
  getTranscriptionStatus,
  checkOllamaStatus,
  suggestVisualInserts,
  generateAutoEditReel
} from '../services/api';
import { recalculateTimeline } from '../utils/timeline';
import { interpretWithOllama } from '../services/api';
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
  Minimize2,
  Subtitles,
  Layers,
  Wand2,
} from 'lucide-react';

interface StudioPageProps {
  onBackToHome: () => void;
}

const STORAGE_KEY = 'rayflow_project_state_v3';

export const StudioPage: React.FC<StudioPageProps> = ({ onBackToHome }) => {
  // Project State
  const [projectName, setProjectName] = useState('Untitled Reel');
  const [hasHydrated, setHasHydrated] = useState(false);
  const [activeTab, setActiveTab] = useState<'photos' | 'music' | 'effects' | 'style' | 'title' | 'captions' | 'inserts'>('photos');

  // Media State
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [audio, setAudio] = useState<UploadedAudio | null>(null);
  const [audioAnalysis, setAudioAnalysis] = useState<AudioAnalysisResult | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isAnalyzingAudio, setIsAnalyzingAudio] = useState(false);

  // Audio preview playback in media library
  const [isAudioPreviewPlaying, setIsAudioPreviewPlaying] = useState(false);
  const mediaAudioRef = useRef<HTMLAudioElement | null>(null);

  // Speech Transcription State (Faster-Whisper)
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcriptionProgress, setTranscriptionProgress] = useState(0);

  // Ollama Client State
  const [ollamaStatus, setOllamaStatus] = useState<{ available: boolean; host: string; models: string[]; default_model?: string }>({
    available: false,
    host: 'http://127.0.0.1:11434',
    models: []
  });
  const [selectedOllamaModel, setSelectedOllamaModel] = useState<string>('');

  // Auto-Edit Workflow Modal State
  const [isAutoEditModalOpen, setIsAutoEditModalOpen] = useState(false);
  const [autoEditStyle, setAutoEditStyle] = useState<'fitness_energy' | 'minimalist' | 'cinematic'>('fitness_energy');
  const [isAutoEditing, setIsAutoEditing] = useState(false);
  const [includeCaptions, setIncludeCaptions] = useState(true);
  const [mobilePanel, setMobilePanel] = useState<'media' | 'director' | null>(null);

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
  const timelineRefreshIdRef = useRef(0);
  const editOriginRef = useRef<EditingPlan | null>(null);
  const planRef = useRef(plan);
  useLayoutEffect(() => { planRef.current = plan; }, [plan]);
  const pollTimersRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set());
  const recognitionRef = useRef<any>(null);

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
  const currentTimeRef = useRef(0.0);
  const lastUiUpdateRef = useRef(0);
  const previewCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const synchronizedAudioRef = useRef<HTMLAudioElement | null>(null);
  const imageCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());
  const videoCacheRef = useRef<Map<string, HTMLVideoElement>>(new Map());
  const drawFrameRef = useRef<(time: number) => void>(() => {});
  const playbackRef = useRef(false);
  useLayoutEffect(() => { playbackRef.current = isPlaying; }, [isPlaying]);
  useEffect(() => () => {
    pollTimersRef.current.forEach(clearInterval);
    recognitionRef.current?.abort();
    videoCacheRef.current.forEach(video => {
      video.pause(); video.removeAttribute('src'); video.load();
    });
  }, []);

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
    setHasHydrated(true);
  }, []);

  // Save state to localStorage on modification
  useEffect(() => {
    if (!hasHydrated) return;
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
  }, [projectName, images, audio, audioAnalysis, plan, hasHydrated]);

  // Push new plan to history
  const updatePlanWithHistory = (newPlan: EditingPlan, recordHistory = true) => {
    if (newPlan.duration_seconds > 120) {
      setErrorMessage('Reels can be up to 120 seconds. Shorten or remove clips first.');
      return;
    }
    timelineRefreshIdRef.current++;
    setViewRenderedVideo(false);
    if (recordHistory) {
      const before = editOriginRef.current || planRef.current;
      if (JSON.stringify(before) !== JSON.stringify(newPlan)) {
        setHistory(prev => [...prev.slice(-25), before]);
        setRedoStack([]);
      }
      editOriginRef.current = null;
    } else if (!editOriginRef.current) {
      editOriginRef.current = planRef.current;
    }
    planRef.current = newPlan;
    setPlan(newPlan);
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setRedoStack(prev => [plan, ...prev]);
    setHistory(prev => prev.slice(0, -1));
    timelineRefreshIdRef.current++;
    editOriginRef.current = null;
    setViewRenderedVideo(false);
    setPlan(previous);
  };

  const handleRedo = () => {
    if (redoStack.length === 0) return;
    const next = redoStack[0];
    setHistory(prev => [...prev, plan]);
    setRedoStack(prev => prev.slice(1));
    timelineRefreshIdRef.current++;
    editOriginRef.current = null;
    setViewRenderedVideo(false);
    setPlan(next);
  };

  // Re-generate timeline whenever plan, images, or audio changes
  const refreshTimeline = async (
    currentPlan: EditingPlan,
    currentImages: UploadedImage[],
    currentAudio: UploadedAudio | null,
    rebuildTimeline = true
  ) => {
    const refreshId = ++timelineRefreshIdRef.current;
    if (currentImages.length === 0) {
      if (refreshId !== timelineRefreshIdRef.current) return;
      setPlan(prev => ({ ...prev, clips: [], transitions: [] }));
      return;
    }

    // Audio changes do not alter the user's visual edit. Rebuilding here used
    // to discard trims, ordering, transitions, and effects after an audio
    // upload/removal.
    if (!rebuildTimeline && currentPlan.clips.length > 0) {
      setPlan(currentPlan);
      return;
    }

    try {
      const updated = await generateProjectPlan(
        currentPlan,
        currentImages.map(img => img.filename),
        currentAudio ? currentAudio.filename : undefined
      );
      if (refreshId !== timelineRefreshIdRef.current) return;
      if (!updated.fit_mode) updated.fit_mode = currentPlan.fit_mode || 'fill';
      if (!updated.transitions) updated.transitions = currentPlan.transitions || [];
      updatePlanWithHistory(updated);
    } catch (err: any) {
      if (refreshId !== timelineRefreshIdRef.current) return;
      setErrorMessage('Could not build the timeline: ' + err.message);
    }
  };

  // Decode media once and repaint paused frames when loading/seeking completes.
  useEffect(() => {
    const liveImages = new Set<string>();
    const liveVideos = new Set<string>();
    for (const clip of plan.clips) {
      if (clip.media_type === 'video') {
        liveVideos.add(clip.id);
        let video = videoCacheRef.current.get(clip.id);
        if (!video || video.dataset.source !== clip.image_url) {
          video?.pause();
          video = document.createElement('video');
          video.crossOrigin = 'anonymous';
          video.playsInline = true;
          video.preload = 'auto';
          video.dataset.source = clip.image_url;
          video.src = getMediaUrl(clip.image_url);
          video.onloadeddata = video.onseeked = () => drawFrameRef.current(currentTimeRef.current);
          video.onerror = () => setErrorMessage('Could not load video: ' + clip.image_url);
          videoCacheRef.current.set(clip.id, video);
          video.load();
        }
      } else liveImages.add(clip.image_url);
    }
    for (const insert of plan.visual_inserts || []) liveImages.add(insert.asset_url);
    liveImages.forEach(url => {
      if (!imageCacheRef.current.has(url)) {
        const image = new Image();
        image.crossOrigin = 'anonymous';
        image.onload = () => drawFrameRef.current(currentTimeRef.current);
        image.onerror = () => setErrorMessage('Could not load image: ' + url);
        image.src = getMediaUrl(url);
        imageCacheRef.current.set(url, image);
      }
    });
    imageCacheRef.current.forEach((image, key) => {
      if (!liveImages.has(key)) { image.onload = null; imageCacheRef.current.delete(key); }
    });
    videoCacheRef.current.forEach((video, key) => {
      if (!liveVideos.has(key)) {
        video.pause(); video.removeAttribute('src'); video.load(); videoCacheRef.current.delete(key);
      }
    });
  }, [plan.clips, plan.visual_inserts]);

  const clipMedia = (clip: ClipConfig, time: number): HTMLImageElement | HTMLVideoElement | undefined => {
    if (clip.media_type !== 'video') return imageCacheRef.current.get(clip.image_url);
    const video = videoCacheRef.current.get(clip.id);
    if (!video) return;
    const target = Math.max(0, Math.min((clip.source_start || 0) + Math.max(0, time - clip.start_time),
      Number.isFinite(video.duration) ? Math.max(0, video.duration - 1 / 30) : Infinity));
    const active = time >= clip.start_time && time < clip.start_time + clip.duration;
    const shouldPlay = active && playbackRef.current;
    video.muted = Boolean(audio) || !active;
    if (video.readyState >= 1 && !video.seeking && Math.abs(video.currentTime - target) > (shouldPlay ? 0.12 : 1 / 60)) {
      video.currentTime = target;
    }
    if (shouldPlay && video.paused) video.play().catch(() => {});
    else if (!shouldPlay && !video.paused) video.pause();
    return video;
  };
  const mediaReady = (media?: HTMLImageElement | HTMLVideoElement) => media instanceof HTMLVideoElement
    ? media.readyState >= 2 : Boolean(media?.complete && media.naturalWidth > 0);

  // Photo Upload Handler with validation
  const processImageFiles = async (fileList: File[]) => {
    const validExtensions = ['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.webm', '.avi', '.mkv'];
    const validFiles = fileList.filter(file => {
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      return validExtensions.includes(ext);
    });

    if (validFiles.length !== fileList.length || validFiles.length === 0) {
      setErrorMessage('Use JPG, PNG, WebP, MP4, MOV or WebM media files.');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadImages(validFiles);
      const combined = [...images, ...uploaded];
      setImages(combined);
      if (planRef.current.clips.length) {
        let start = planRef.current.duration_seconds;
        const appended: ClipConfig[] = uploaded.map(item => {
          const duration = item.media_type === 'video' ? Math.min(10, item.duration || 3) : 2.5;
          const clip: ClipConfig = { id: crypto.randomUUID(), image_url: item.url, start_time: start,
            duration, media_type: item.media_type || 'image', motion: item.media_type === 'video' ? 'static' : 'zoom_in', transition: 'none' };
          start += duration;
          return clip;
        });
        updatePlanWithHistory(recalculateTimeline([...planRef.current.clips, ...appended], planRef.current.transitions, planRef.current));
      } else await refreshTimeline(planRef.current, combined, audio);
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
    e.target.value = '';
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
        await refreshTimeline(plan, images, uploaded, false);
        setConversation(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: `Soundtrack "${uploaded.original_name}" loaded. Librosa detected ${analysis.tempo} BPM with ${analysis.beat_count} rhythm beats. Your timeline edits were preserved.`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
      } catch (err: any) {
        console.warn('Audio analysis fallback:', err);
        setAudioAnalysis(null);
        setErrorMessage('Soundtrack uploaded, but beat analysis failed. ' + err.message);
        await refreshTimeline(plan, images, uploaded, false);
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
    const removed = images[index];
    updatePlanWithHistory(recalculateTimeline(plan.clips.filter(c => getMediaUrl(c.image_url) !== getMediaUrl(removed.url)), plan.transitions, {
      ...plan, visual_inserts: (plan.visual_inserts || []).filter(i => getMediaUrl(i.asset_url) !== getMediaUrl(removed.url))
    }));
  };

  const handleMoveImage = (index: number, direction: 'up' | 'down') => {
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= images.length) return;
    const copy = [...images];
    const [moved] = copy.splice(index, 1);
    copy.splice(target, 0, moved);
    setImages(copy);
    const rank = new Map(copy.map((item, i) => [getMediaUrl(item.url), i]));
    const ordered = [...plan.clips].sort((a, b) => (rank.get(getMediaUrl(a.image_url)) ?? 0) - (rank.get(getMediaUrl(b.image_url)) ?? 0));
    updatePlanWithHistory(recalculateTimeline(ordered, plan.transitions, plan));
  };

  const handleRemoveAudio = () => {
    if (isAudioPreviewPlaying && mediaAudioRef.current) {
      mediaAudioRef.current.pause();
      setIsAudioPreviewPlaying(false);
    }
    setAudio(null);
    setAudioAnalysis(null);
    refreshTimeline(plan, images, null, false);
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
    setMobilePanel('media');
  };

  // Check local Ollama status on mount
  useEffect(() => {
    checkOllamaStatus()
      .then(st => {
        setOllamaStatus(st);
        if (st.models && st.models.length > 0) {
          setSelectedOllamaModel(st.default_model || st.models[0]);
        }
      })
      .catch(() => {});
  }, []);

  // Speech-to-Text Transcription via local Faster-Whisper
  const handleAutoTranscribe = async () => {
    const speechSource = audio?.filename || images.find(item => item.media_type === 'video')?.filename;
    if (!speechSource) {
      setErrorMessage('Please upload speech audio or video first.');
      return;
    }
    setIsTranscribing(true);
    setTranscriptionProgress(0);
    setErrorMessage(null);
    try {
      const jobId = await startTranscription(speechSource, 'tiny');
      setTranscriptionProgress(0);

      const pollTimer = setInterval(async () => {
        try {
          const job = await getTranscriptionStatus(jobId);
          if (job.status === 'processing') {
            setTranscriptionProgress(Math.round(job.progress || 50));
          } else if (job.status === 'completed') {
            clearInterval(pollTimer);
            setIsTranscribing(false);
            setTranscriptionProgress(100);
            if (job.subtitles && job.subtitles.length > 0) {
              const updatedPlan: EditingPlan = {
                ...planRef.current,
                subtitles: job.subtitles
              };
              updatePlanWithHistory(updatedPlan);
              setActiveTab('captions');
              setConversation(prev => [
                ...prev,
                {
                  sender: 'assistant',
                  text: `Faster-Whisper transcribed audio locally with int8 quantization. Generated ${job.subtitles.length} subtitle segments with word-level timestamps and keyword highlights.`,
                  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
              ]);
            }
          } else if (job.status === 'failed') {
            clearInterval(pollTimer);
            setIsTranscribing(false);
            setErrorMessage(`Transcription failed: ${job.error || 'Unknown error'}`);
          }
        } catch (e: any) {
          clearInterval(pollTimer);
          setIsTranscribing(false);
          setErrorMessage(`Transcription status error: ${e.message}`);
        }
      }, 1200);
      pollTimersRef.current.add(pollTimer);
    } catch (err: any) {
      setIsTranscribing(false);
      setErrorMessage(err.message || 'Failed to start local transcription.');
    }
  };

  // Contextual Visual Inserts Suggestion from Subtitles
  const handleAutoSuggestInserts = async () => {
    if (!plan.subtitles || plan.subtitles.length === 0) {
      setErrorMessage('No subtitles available. Transcribe speech first.');
      return;
    }
    if (images.length === 0) {
      setErrorMessage('Please upload photos or B-roll images first.');
      return;
    }
    try {
      const assets = images.map(img => ({
        id: img.filename,
        filename: img.filename,
        original_name: img.original_name,
        url: img.url
      }));
      const suggested = await suggestVisualInserts(plan.subtitles, assets, 'pip');
      if (suggested && suggested.length > 0) {
        updatePlanWithHistory({
          ...plan,
          visual_inserts: suggested
        });
        setActiveTab('inserts');
        setConversation(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: `Matched ${suggested.length} contextual visual inserts from your media library based on speech transcript keywords.`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
      } else {
        setErrorMessage('No matching keywords found between transcript and uploaded images.');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to suggest visual inserts.');
    }
  };

  // Automatic Talking-Head / Photo Reel Generation Workflow
  const handleExecuteAutoEdit = async () => {
    if (images.length === 0) {
      setErrorMessage('Please upload photographs or an audio/video soundtrack to generate an auto reel.');
      return;
    }
    setIsAutoEditing(true);
    setErrorMessage(null);
    try {
      const assets = images.map(img => ({
        id: img.filename,
        filename: img.filename,
        original_name: img.original_name,
        url: img.url
      }));
      const video = images.find(item => item.media_type === 'video');
      const mediaTarget = video?.filename || audio?.filename || images[0].filename;
      const newPlan = await generateAutoEditReel(mediaTarget, autoEditStyle, assets, 'tiny', plan.aspect_ratio, includeCaptions);
      setIsPlaying(false);
      currentTimeRef.current = 0;
      setCurrentTime(0);
      setErrorMessage(newPlan.warnings?.join(' ') || null);
      updatePlanWithHistory(newPlan);
      setIsAutoEditModalOpen(false);
      if (newPlan.subtitles && newPlan.subtitles.length > 0) {
        setActiveTab('captions');
      } else {
        setActiveTab('photos');
      }
      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `Auto Reel draft generated! Applied "${autoEditStyle.replace('_', ' ').toUpperCase()}" style, synchronized ${newPlan.clips.length} clip cuts, and structured your timeline.`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Auto reel generation failed.');
    } finally {
      setIsAutoEditing(false);
    }
  };

  // Voice Recognition via Web Speech API
  const handleVoiceToggle = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setErrorMessage('Speech recognition is not supported in this browser. Please type your direction.');
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognitionRef.current = recognition;
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
      const res = ollamaStatus.available && selectedOllamaModel
        ? await interpretWithOllama(cmd, plan, selectedOllamaModel)
        : await interpretNaturalCommand(cmd, plan);
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
    if (plan.clips.length === 0) {
      setErrorMessage('Add at least one clip to the timeline before exporting.');
      return;
    }

    setIsRenderingModalOpen(true);
    setRenderStatus(null);
    setRenderJobId(null);
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
        } catch (error: any) {
          clearInterval(interval);
          setRenderStatus(prev => prev ? { ...prev, status: 'failed', error: 'Could not retrieve export status: ' + error.message } : prev);
        }
      }, 1200);
      pollTimersRef.current.add(interval);
    } catch (err: any) {
      setErrorMessage(err.message || 'Render failed to start.');
      setIsRenderingModalOpen(false);
    }
  };

  // Helper to draw an image frame onto the preview canvas
  const drawImageFrame = (
    ctx: CanvasRenderingContext2D,
    img: HTMLImageElement | HTMLVideoElement,
    clip: ClipConfig,
    w: number,
    h: number,
    progress: number,
    alpha: number = 1.0
  ) => {
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));

    const fitMode = plan.fit_mode || 'fill';
    const naturalWidth = img instanceof HTMLVideoElement ? img.videoWidth : img.naturalWidth;
    const naturalHeight = img instanceof HTMLVideoElement ? img.videoHeight : img.naturalHeight;
    let scale: number;
    let zoom = 1.0;

    if (fitMode === 'fit') {
      // Fit mode: preserve whole image, centered
      scale = Math.min(w / naturalWidth, h / naturalHeight);
    } else {
      // Fill mode: crop to cover and apply motion zoom
      scale = Math.max(w / naturalWidth, h / naturalHeight);
      if (clip.media_type !== 'video' && clip.motion === 'zoom_out') {
        zoom = 1.15 - 0.1 * progress;
      } else if (clip.media_type !== 'video' && clip.motion === 'zoom_in') {
        zoom = 1.05 + 0.1 * progress;
      }
    }

    const finalScale = scale * zoom;
    const pan = fitMode === 'fill' && clip.media_type !== 'video' && (clip.motion === 'pan_left' || clip.motion === 'pan_right');
    const sw = naturalWidth * (pan ? scale * 1.15 : finalScale);
    const sh = naturalHeight * (pan ? scale * 1.15 : finalScale);
    const sx = (w - sw) / 2 + (pan ? w * 0.15 * (0.5 - (clip.motion === 'pan_left' ? 1 - progress : progress)) : 0);
    const sy = (h - sh) / 2;

    ctx.drawImage(img, sx, sy, sw, sh);
    ctx.restore();
  };

  // Direct canvas render function decoupled from React rendering cycle
  const renderPreviewFrame = (time: number) => {
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

    videoCacheRef.current.forEach((video, id) => {
      const clip = plan.clips.find(c => c.id === id);
      if (!clip || time < clip.start_time || time >= clip.start_time + clip.duration) video.pause();
    });
    const clipIdx = plan.clips.findIndex(
      c => time >= c.start_time && time < c.start_time + c.duration
    );
    const activeClip = clipIdx >= 0 ? plan.clips[clipIdx] : (plan.clips.length > 0 ? plan.clips[plan.clips.length - 1] : null);

    if (activeClip && activeClip.image_url) {
      const cached = clipMedia(activeClip, time);
      if (cached && mediaReady(cached)) {
        const clipProgress = activeClip.duration > 0
          ? Math.min(1, Math.max(0, (time - activeClip.start_time) / activeClip.duration))
          : 0;

        // Check if a transition is active with the next clip
        let transitionHandled = false;
        if (clipIdx >= 0 && clipIdx < plan.clips.length - 1) {
          const nextClip = plan.clips[clipIdx + 1];
          const boundaryTrans = (plan.transitions || []).find(
            t => t.from_clip_id === activeClip.id && t.to_clip_id === nextClip.id
          );

          if (boundaryTrans && boundaryTrans.enabled && boundaryTrans.type !== 'none') {
            const tDur = Math.round(Math.max(0, Math.min(boundaryTrans.duration, activeClip.duration - 0.1, nextClip.duration - 0.1, 2)) * 30) / 30;
            const clipEnd = activeClip.start_time + activeClip.duration;
            const tStart = clipEnd - tDur;

            if (time >= tStart && time < clipEnd) {
              const transProgress = (time - tStart) / tDur;
              const nextCached = clipMedia(nextClip, time);

              if (boundaryTrans.type === 'crossfade') {
                drawImageFrame(ctx, cached, activeClip, w, h, clipProgress, 1.0);
                if (nextCached && mediaReady(nextCached)) {
                  drawImageFrame(ctx, nextCached, nextClip, w, h, 0, transProgress);
                }
                transitionHandled = true;
              } else if (['dip_black', 'fade_in', 'fade_out'].includes(boundaryTrans.type)) {
                if (transProgress < 0.5) {
                  drawImageFrame(ctx, cached, activeClip, w, h, clipProgress, 1.0);
                  ctx.fillStyle = `rgba(0, 0, 0, ${transProgress * 2})`;
                  ctx.fillRect(0, 0, w, h);
                } else {
                  if (nextCached && mediaReady(nextCached)) {
                    drawImageFrame(ctx, nextCached, nextClip, w, h, 0, 1.0);
                  }
                  ctx.fillStyle = `rgba(0, 0, 0, ${(1 - transProgress) * 2})`;
                  ctx.fillRect(0, 0, w, h);
                }
                transitionHandled = true;
              } else if (boundaryTrans.type === 'dip_white') {
                if (transProgress < 0.5) {
                  drawImageFrame(ctx, cached, activeClip, w, h, clipProgress, 1.0);
                  ctx.fillStyle = `rgba(255, 255, 255, ${transProgress * 2})`;
                  ctx.fillRect(0, 0, w, h);
                } else {
                  if (nextCached && mediaReady(nextCached)) {
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
          drawImageFrame(ctx, cached, activeClip, w, h, clipProgress, 1.0);
        }

        // Global Head Transition (Fade in from black)
        if (plan.head_transition?.enabled) {
          const hDur = Math.max(1 / 30, Math.min(plan.head_transition.duration || 0.5, plan.duration_seconds / 3));
          if (time < hDur) {
            const hAlpha = 1.0 - (time / hDur);
            ctx.fillStyle = plan.head_transition.type?.includes('white') ? '#FFFFFF' : '#000000';
            ctx.globalAlpha = Math.max(0, Math.min(1, hAlpha));
            ctx.fillRect(0, 0, w, h);
            ctx.globalAlpha = 1.0;
          }
        }

        // Global Tail Transition (Fade out to black)
        if (plan.tail_transition?.enabled) {
          const tDur = Math.max(1 / 30, Math.min(plan.tail_transition.duration || 0.5, plan.duration_seconds / 3));
          const tStart = Math.max(0, plan.duration_seconds - tDur);
          if (time > tStart) {
            const tAlpha = (time - tStart) / tDur;
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
        if (plan.title.enabled && plan.title.text && time < 4.5) {
          ctx.save();
          ctx.globalAlpha = 1;

          ctx.textAlign = 'center';
          const fontSize = Math.max(28, Math.round(w * 0.055));
          ctx.font = `600 ${fontSize}px Inter, -apple-system, sans-serif`;

          // Soft drop shadow for legibility on any image
          ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
          ctx.shadowBlur = 8;
          ctx.shadowOffsetY = 2;

          ctx.fillStyle = '#FFFFFF';
          const titleY = plan.title.position === 'top' ? h * 0.15 : plan.title.position === 'bottom' ? h * 0.8 : h * 0.45;
          ctx.fillText(plan.title.text, w / 2, titleY);

          if (plan.title.subtitle) {
            ctx.font = `400 ${Math.max(14, Math.round(w * 0.026))}px Inter, -apple-system, sans-serif`;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
            ctx.fillText(plan.title.subtitle, w / 2, titleY + fontSize * 0.9);
          }
          ctx.restore();
        }

        // Render Active Visual Inserts (Stage 6)
        if (plan.visual_inserts && plan.visual_inserts.length > 0) {
          const activeIns = plan.visual_inserts.find(ins => time >= ins.start_time && time <= ins.start_time + ins.duration);
          if (activeIns) {
            const insUrl = activeIns.asset_url;
            let imgEl = imageCacheRef.current.get(insUrl);
            if (!imgEl) {
              imgEl = new Image();
              imgEl.src = getMediaUrl(insUrl);
              imageCacheRef.current.set(insUrl, imgEl);
            }
            if (imgEl.complete && imgEl.naturalWidth > 0) {
              ctx.save();
              if (activeIns.mode === 'cutaway') {
                ctx.drawImage(imgEl, 0, 0, w, h);
              } else if (activeIns.mode === 'split') {
                const hw = Math.round(w / 2);
                ctx.drawImage(imgEl, hw, 0, hw, h);
              } else {
                // PIP overlay with clean border
                const pipW = Math.round(w * 0.38);
                const pipH = Math.round(pipW * (imgEl.naturalHeight / imgEl.naturalWidth));
                let px = Math.round(w * 0.57);
                let py = Math.round(h * 0.08);
                if (activeIns.position === 'top_left') {
                  px = Math.round(w * 0.05);
                } else if (activeIns.position === 'bottom_right') {
                  py = Math.round(h * 0.70);
                } else if (activeIns.position === 'center') {
                  px = Math.round((w - pipW) / 2);
                  py = Math.round((h - pipH) / 2);
                }
                ctx.fillStyle = '#FFFFFF';
                ctx.fillRect(px - 3, py - 3, pipW + 6, pipH + 6);
                ctx.drawImage(imgEl, px, py, pipW, pipH);
              }
              ctx.restore();
            }
          }
        }

        // Render Dynamic Subtitles (Stage 4)
        if (plan.subtitles && plan.subtitles.length > 0) {
          const activeSub = plan.subtitles.find(s => time >= s.start_time && time <= s.end_time);
          if (activeSub) {
            ctx.save();
            const subStyle = activeSub.style || {
              preset: 'bold_pop',
              caption_mode: 'word_by_word',
              font_size: 42,
              color: '#FFFFFF',
              highlight_color: '#FACC15',
              stroke_color: '#000000',
              stroke_width: 4,
              position: 'center_bottom'
            };
            const isWordByWord = (subStyle.caption_mode || 'word_by_word') === 'word_by_word';
            const baseFontSize = (subStyle.font_size || 42) * w / (ratio === '16:9' ? 1920 : 1080);
            const primaryColor = subStyle.color || '#FFFFFF';
            const highlightColor = subStyle.highlight_color || '#FACC15';
            const strokeColor = subStyle.stroke_color || '#000000';
            const strokeWidth = (subStyle.stroke_width ?? 3) * w / (ratio === '16:9' ? 1920 : 1080);

            const yPos = subStyle.position === 'top'
              ? h * 0.12
              : subStyle.position === 'middle'
              ? h * 0.50
              : h * 0.86;

            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.lineJoin = 'round';
            ctx.miterLimit = 2;

            if (isWordByWord && activeSub.words && activeSub.words.length > 0) {
              const activeWord = activeSub.words.find(word => time >= word.start && time < word.end);

              if (activeWord) {
                const isEmph = Boolean(activeWord.emphasis);
                const fontSize = isEmph ? Math.round(baseFontSize * 1.15) : baseFontSize;
                ctx.font = `800 ${fontSize}px Inter, Arial, sans-serif`;

                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = strokeWidth + (isEmph ? 2 : 0);
                const wordText = isEmph ? activeWord.word.toUpperCase() : activeWord.word;
                ctx.strokeText(wordText, w / 2, yPos);

                ctx.fillStyle = isEmph ? highlightColor : primaryColor;
                ctx.fillText(wordText, w / 2, yPos);
              }
            } else {
              // Phrase display
              const fontSize = baseFontSize;
              ctx.font = `700 ${fontSize}px Inter, Arial, sans-serif`;

              if (activeSub.words && activeSub.words.length > 0) {
                const words = activeSub.words;
                const wordMeasures = words.map(item => ({
                  word: item,
                  width: ctx.measureText(item.word + ' ').width
                }));
                const totalWidth = wordMeasures.reduce((acc, curr) => acc + curr.width, 0);
                let currentX = Math.max(10, (w - totalWidth) / 2);

                ctx.textAlign = 'left';
                for (const wm of wordMeasures) {
                  const isEmph = Boolean(wm.word.emphasis);
                  ctx.font = isEmph ? `800 ${Math.round(fontSize * 1.1)}px Inter, Arial, sans-serif` : `700 ${fontSize}px Inter, Arial, sans-serif`;
                  ctx.strokeStyle = strokeColor;
                  ctx.lineWidth = strokeWidth;
                  ctx.strokeText(wm.word.word, currentX, yPos);

                  ctx.fillStyle = isEmph ? highlightColor : primaryColor;
                  ctx.fillText(wm.word.word, currentX, yPos);
                  currentX += wm.width;
                }
              } else {
                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = strokeWidth;
                ctx.strokeText(activeSub.text, w / 2, yPos);

                ctx.fillStyle = primaryColor;
                ctx.fillText(activeSub.text, w / 2, yPos);
              }
            }
            ctx.restore();
          }
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
  };

  useLayoutEffect(() => { drawFrameRef.current = renderPreviewFrame; });

  // Re-draw canvas frame whenever plan or images update
  useEffect(() => {
    drawFrameRef.current(currentTimeRef.current);
  }, [plan, images, viewRenderedVideo]);

  // Real Playback Controller & Canvas Animation Loop
  useEffect(() => {
    let animId: number;
    let lastStamp: number | null = null;

    const tick = (stamp: number) => {
      if (lastStamp !== null && isPlaying) {
        const delta = (stamp - lastStamp) / 1000;
        const next = currentTimeRef.current + delta;

        if (next >= plan.duration_seconds) {
          setIsPlaying(false);
          currentTimeRef.current = plan.duration_seconds;
          setCurrentTime(plan.duration_seconds);
          synchronizedAudioRef.current?.pause();
          videoCacheRef.current.forEach(video => video.pause());
          drawFrameRef.current(plan.duration_seconds);
          return;
        }

        currentTimeRef.current = next;
        if (synchronizedAudioRef.current) synchronizedAudioRef.current.volume = Math.max(0, Math.min(1, (plan.duration_seconds - next) / Math.min(1.5, plan.duration_seconds)));

        // Keep audio synchronized with playback position
        if (synchronizedAudioRef.current && !synchronizedAudioRef.current.paused) {
          const diff = Math.abs(synchronizedAudioRef.current.currentTime - next);
          if (diff > 0.25) {
            synchronizedAudioRef.current.currentTime = next;
          }
        }

        // Direct 60fps canvas render
        drawFrameRef.current(next);

        // Throttle React component tree updates to ~15fps (every 66ms) to avoid lagging UI
        if (stamp - lastUiUpdateRef.current > 66) {
          lastUiUpdateRef.current = stamp;
          setCurrentTime(next);
        }
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
  }, [isPlaying, plan]);

  useEffect(() => {
    if (!isPlaying) {
      synchronizedAudioRef.current?.pause();
      videoCacheRef.current.forEach(video => video.pause());
    }
  }, [isPlaying]);

  useEffect(() => {
    if (currentTimeRef.current > plan.duration_seconds || !plan.clips.length) {
      currentTimeRef.current = plan.clips.length ? plan.duration_seconds : 0;
      setCurrentTime(currentTimeRef.current);
      setIsPlaying(false);
    }
  }, [plan.duration_seconds, plan.clips.length]);

  const handleTogglePlay = () => {
    setViewRenderedVideo(false);
    if (!plan.clips.length) return;
    if (isPlaying) {
      setIsPlaying(false);
      setCurrentTime(currentTimeRef.current);
      if (synchronizedAudioRef.current) {
        synchronizedAudioRef.current.pause();
      }
    } else {
      if (currentTimeRef.current >= plan.duration_seconds - 1 / 30) {
        currentTimeRef.current = 0.0;
        setCurrentTime(0.0);
      }
      if (synchronizedAudioRef.current && audio) {
        synchronizedAudioRef.current.currentTime = currentTimeRef.current;
        synchronizedAudioRef.current.play().catch(e => console.warn('Audio play deferred:', e));
      }
      setIsPlaying(true);
    }
  };

  const handleSeek = (newTime: number) => {
    newTime = Math.max(0, Math.min(plan.duration_seconds, newTime));
    setViewRenderedVideo(false);
    currentTimeRef.current = newTime;
    setCurrentTime(newTime);
    if (synchronizedAudioRef.current && audio) {
      synchronizedAudioRef.current.currentTime = newTime;
    }
    renderPreviewFrame(newTime);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement;
      if (element.matches('input, textarea, select, [contenteditable="true"]')) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey) handleRedo(); else handleUndo();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
        event.preventDefault(); handleRedo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const resizeDuration = (duration: number) => {
    if (!plan.clips.length) { updatePlanWithHistory({ ...plan, duration_seconds: duration }); return; }
    const target = Math.max(duration, plan.clips.length * 0.5);
    const flexible = plan.clips.reduce((sum, clip) => sum + Math.max(0, clip.duration - 0.5), 0);
    const resized = plan.clips.map(clip => ({ ...clip, duration: 0.5 + (target - plan.clips.length * 0.5) *
      (flexible ? Math.max(0, clip.duration - 0.5) / flexible : 1 / plan.clips.length) }));
    updatePlanWithHistory(recalculateTimeline(resized, plan.transitions, plan));
  };

  const repace = (updated: EditingPlan, keepDuration = false) => {
    const originals = updated.clips;
    if (!originals.length) { updatePlanWithHistory(updated); return; }
    const seconds = updated.cut_pacing === 'fast' ? 1.5 : updated.cut_pacing === 'slow' ? 4 : 2.5;
    const duration = keepDuration ? updated.duration_seconds : Math.min(120, originals.length * seconds);
    let cursor = 0;
    const clips = originals.map((clip, i) => {
      let end = duration * (i + 1) / originals.length;
      if (updated.beat_sync && audioAnalysis?.beat_times.length && i < originals.length - 1) {
        const candidates = audioAnalysis.beat_times.filter(t => t >= cursor + 0.5 && t <= duration - (originals.length - i - 1) * 0.5);
        if (candidates.length) end = candidates.reduce((best, t) => Math.abs(t - end) < Math.abs(best - end) ? t : best);
      }
      const length = i === originals.length - 1 ? duration - cursor : Math.max(0.5, end - cursor);
      cursor += length;
      return { ...clip, duration: length };
    });
    updatePlanWithHistory(recalculateTimeline(clips, updated.transitions, updated));
  };

  return (
    <div className="flex flex-col h-dvh bg-white text-zinc-900 select-none overflow-hidden">
      {/* Hidden audio element for preview sync */}
      {audio && (
        <audio
          ref={synchronizedAudioRef}
          src={getMediaUrl(audio.url)}
          preload="auto"
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
      <header className="h-14 gap-4 overflow-x-auto border-b border-zinc-200 bg-white px-3 flex items-center justify-between z-30 shrink-0">
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
              className="w-28 text-sm font-semibold text-zinc-900 bg-transparent border-b border-transparent hover:border-zinc-300 focus:border-zinc-900 focus:outline-none transition-colors px-1"
              title="Click to rename project"
            />
          </div>
        </div>

        {/* Center: Aspect Ratio & Image Fit Mode Controls */}
        <div className="flex shrink-0 items-center gap-3">
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

        <div className="flex shrink-0 gap-2">
          <button className="lg:hidden text-xs border rounded px-2 py-1" onClick={() => setMobilePanel(mobilePanel === 'media' ? null : 'media')}>Media</button>
          <button className="xl:hidden text-xs border rounded px-2 py-1" onClick={() => setMobilePanel(mobilePanel === 'director' ? null : 'director')}>Director</button>
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
                  setIsPlaying(false);
                  currentTimeRef.current = 0;
                  setCurrentTime(0);
                  setHistory([]);
                  setRedoStack([]);
                  setSelectedClipId(null);
                  setViewRenderedVideo(false);
                  setRenderStatus(null);
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
            variant="secondary"
            size="sm"
            onClick={() => setIsAutoEditModalOpen(true)}
            className="flex items-center gap-1.5 border-amber-300 hover:border-amber-400 bg-amber-50/50 hover:bg-amber-100/60 text-amber-900"
            title="Automatically transcribe and generate a dynamic talking-head reel"
          >
            <Wand2 className="w-3.5 h-3.5 text-amber-600" />
            <span className="font-semibold">Auto Reel</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleStartRender}
            disabled={plan.clips.length === 0 || renderStatus?.status === 'processing' || renderStatus?.status === 'queued'}
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export MP4</span>
          </Button>
        </div>
      </header>

      {errorMessage && (
        <div role="alert" className="shrink-0 max-h-20 overflow-auto border-b border-zinc-200 px-3 py-2 text-xs bg-white flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /><span className="flex-1">{errorMessage}</span>
          <button aria-label="Dismiss message" onClick={() => setErrorMessage(null)}>Dismiss</button>
        </div>
      )}
      {/* Main Studio Area (3 Columns: Left Media/Settings, Center Preview, Right AI Assistant) */}
      <div className="flex-1 min-h-0 flex relative overflow-hidden">
        {/* LEFT PANEL: Media Library & Settings */}
        <aside className={`${mobilePanel === 'media' ? 'flex absolute inset-y-0 left-0 z-30 shadow-xl' : 'hidden'} lg:static lg:flex w-72 max-w-[85vw] border-r border-zinc-200 bg-zinc-50 flex-col shrink-0 overflow-hidden`}>
          <button className="lg:hidden text-xs p-2 border-b" onClick={() => setMobilePanel(null)}>Close media</button>
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
              <span>Media ({images.length})</span>
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
              onClick={() => setActiveTab('captions')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'captions'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
              title="Dynamic Expressive Captions"
            >
              <Subtitles className="w-3.5 h-3.5 text-amber-500" />
              <span>Captions {plan.subtitles && plan.subtitles.length > 0 ? `(${plan.subtitles.length})` : ''}</span>
            </button>

            <button
              onClick={() => setActiveTab('inserts')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'inserts'
                  ? 'border-zinc-900 text-zinc-900 font-semibold bg-zinc-50'
                  : 'border-transparent text-zinc-500 hover:text-zinc-900'
              }`}
              title="Contextual B-Roll & Visual Inserts"
            >
              <Layers className="w-3.5 h-3.5 text-blue-500" />
              <span>Inserts {plan.visual_inserts && plan.visual_inserts.length > 0 ? `(${plan.visual_inserts.length})` : ''}</span>
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
                    Add Photos or Videos
                  </span>
                  <span className="text-[11px] text-zinc-500 mt-0.5">
                    Drag and drop JPG, PNG, WebP, MP4, MOV or WebM files
                  </span>
                  <input
                    type="file"
                    multiple
                    accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.avi,.mkv"
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
                    <p className="font-medium text-zinc-700">No media in project library</p>
                    <p className="text-[11px]">Upload photos or videos to begin assembling your reel.</p>
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
                          {img.media_type === 'video'
                            ? <video src={getMediaUrl(img.url)} muted preload="metadata" className="w-10 h-10 object-cover rounded shrink-0" />
                            : <img src={getMediaUrl(img.url)} alt="" className="w-10 h-10 object-cover rounded shrink-0" />}
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
                      if (updated.beat_sync && !audioAnalysis?.beat_times.length) { setErrorMessage('Analyze a soundtrack with detectable beats first.'); return; }
                      repace(updated, true);
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
                          repace(updated);
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
                      resizeDuration(parseFloat(e.target.value));
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

            {/* CAPTIONS TAB (Stage 4) */}
            {activeTab === 'captions' && (
              <div className="space-y-4">
                {/* Auto-Transcribe Action Card */}
                <div className="p-3.5 bg-amber-500/10 border border-amber-200 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-950 flex items-center gap-1.5">
                      <Subtitles className="w-4 h-4 text-amber-600" />
                      Local Speech Transcription
                    </span>
                    <span className="text-[10px] font-mono bg-amber-200/60 text-amber-900 px-1.5 py-0.5 rounded font-semibold">
                      Faster-Whisper
                    </span>
                  </div>
                  <p className="text-[11px] text-amber-800 leading-relaxed">
                    Extract word-level timestamps and auto-highlight high-energy emphasis keywords on CPU without paid APIs.
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAutoTranscribe}
                    disabled={isTranscribing || (!audio && !images.some(item => item.media_type === 'video'))}
                    className="w-full bg-amber-600 hover:bg-amber-700 text-white flex items-center justify-center gap-1.5 shadow-xs"
                  >
                    {isTranscribing ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Transcribing... {transcriptionProgress}%</span>
                      </>
                    ) : (
                      <>
                        <Mic className="w-3.5 h-3.5" />
                        <span>Transcribe Speech from Media</span>
                      </>
                    )}
                  </Button>
                </div>

                {/* Caption Presets */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-900 block">
                    Caption Style Preset
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'bold_pop', name: 'Bold Pop', color: '#FACC15', desc: 'Neon Yellow Active Pop' },
                      { id: 'fitness_energy', name: 'Fitness Energy', color: '#38BDF8', desc: 'Electric Cyan & Amber' },
                      { id: 'minimalist', name: 'Minimalist Clean', color: '#E11D48', desc: 'Subtle Crimson Accent' },
                      { id: 'subtle_border', name: 'Subtle Border', color: '#10B981', desc: 'Clean Emerald Stroke' },
                    ].map(preset => {
                      const currentPreset = plan.subtitles?.[0]?.style?.preset || 'bold_pop';
                      const isSelected = currentPreset === preset.id;
                      return (
                        <button
                          key={preset.id}
                          onClick={() => {
                            if (!plan.subtitles || plan.subtitles.length === 0) return;
                            const updatedSubs = plan.subtitles.map(s => ({
                              ...s,
                              style: {
                                ...(s.style || {
                                  preset: 'bold_pop' as SubtitlePreset,
                                  font_size: 42,
                                  font_family: 'Inter, sans-serif',
                                  color: '#FFFFFF',
                                  highlight_color: '#FACC15',
                                  stroke_color: '#000000',
                                  stroke_width: 4,
                                  position: 'center_bottom' as const
                                }),
                                preset: preset.id as SubtitlePreset,
                                highlight_color: preset.color,
                                caption_mode: preset.id === 'minimalist' || preset.id === 'subtle_border' ? 'phrase' as const : 'word_by_word' as const
                              }
                            }));
                            updatePlanWithHistory({ ...plan, subtitles: updatedSubs });
                          }}
                          className={`p-2.5 rounded-xl border text-left transition-all ${
                            isSelected
                              ? 'bg-zinc-900 text-white border-zinc-900 shadow-sm ring-1 ring-zinc-900'
                              : 'bg-white text-zinc-800 border-zinc-200 hover:border-zinc-300'
                          }`}
                        >
                          <div className="flex items-center gap-1.5 mb-1">
                            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: preset.color }} />
                            <span className="text-xs font-semibold">{preset.name}</span>
                          </div>
                          <p className={`text-[10px] leading-tight ${isSelected ? 'text-zinc-300' : 'text-zinc-500'}`}>
                            {preset.desc}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Caption Mode Switcher */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-900 block">
                    Timing Display Mode
                  </label>
                  <div className="grid grid-cols-2 gap-2 p-1 bg-zinc-100 rounded-lg border border-zinc-200">
                    <button
                      onClick={() => {
                        if (!plan.subtitles) return;
                        const updated = plan.subtitles.map(s => ({
                          ...s,
                          style: { ...(s.style || {
                            preset: 'bold_pop' as SubtitlePreset,
                            font_size: 42,
                            font_family: 'Inter, sans-serif',
                            color: '#FFFFFF',
                            highlight_color: '#FACC15',
                            stroke_color: '#000000',
                            stroke_width: 4,
                            position: 'center_bottom' as const
                          }), caption_mode: 'word_by_word' as const }
                        }));
                        updatePlanWithHistory({ ...plan, subtitles: updated });
                      }}
                      className={`py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                        (plan.subtitles?.[0]?.style?.caption_mode || 'word_by_word') === 'word_by_word'
                          ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                          : 'text-zinc-600 hover:text-zinc-900'
                      }`}
                    >
                      Word-by-Word
                    </button>
                    <button
                      onClick={() => {
                        if (!plan.subtitles) return;
                        const updated = plan.subtitles.map(s => ({
                          ...s,
                          style: { ...(s.style || {
                            preset: 'bold_pop' as SubtitlePreset,
                            font_size: 42,
                            font_family: 'Inter, sans-serif',
                            color: '#FFFFFF',
                            highlight_color: '#FACC15',
                            stroke_color: '#000000',
                            stroke_width: 4,
                            position: 'center_bottom' as const
                          }), caption_mode: 'phrase' as const }
                        }));
                        updatePlanWithHistory({ ...plan, subtitles: updated });
                      }}
                      className={`py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                        plan.subtitles?.[0]?.style?.caption_mode === 'phrase'
                          ? 'bg-white text-zinc-900 font-semibold shadow-xs'
                          : 'text-zinc-600 hover:text-zinc-900'
                      }`}
                    >
                      Full Phrase
                    </button>
                  </div>
                </div>

                {/* Subtitle Segments List */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-zinc-900">
                      Subtitle Segments ({plan.subtitles?.length || 0})
                    </label>
                    <button
                      onClick={() => {
                        const newSub: SubtitleSegment = {
                          id: `sub-${(plan.subtitles?.length || 0) + 1}`,
                          text: 'NEW CAPTION PHRASE',
                          start_time: Math.round(currentTime * 10) / 10,
                          end_time: Math.round((currentTime + 2.0) * 10) / 10,
                          words: [
                            { word: 'NEW', start: currentTime, end: currentTime + 0.6, emphasis: true },
                            { word: 'CAPTION', start: currentTime + 0.6, end: currentTime + 1.3, emphasis: false },
                            { word: 'PHRASE', start: currentTime + 1.3, end: currentTime + 2.0, emphasis: true }
                          ]
                        };
                        updatePlanWithHistory({
                          ...plan,
                          subtitles: [...(plan.subtitles || []), newSub]
                        });
                      }}
                      className="text-[11px] font-semibold text-amber-600 hover:text-amber-700"
                    >
                      + Add Segment
                    </button>
                  </div>

                  <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                    {(plan.subtitles || []).map(seg => (
                      <div
                        key={seg.id}
                        onClick={() => {
                          currentTimeRef.current = seg.start_time;
                          setCurrentTime(seg.start_time);
                          renderPreviewFrame(seg.start_time);
                        }}
                        className="p-2.5 rounded-lg border border-zinc-200 bg-white hover:border-zinc-300 transition-colors cursor-pointer group"
                      >
                        <div className="flex items-center justify-between text-[11px] text-zinc-400 font-mono mb-1">
                          <span>{seg.start_time.toFixed(1)}s - {seg.end_time.toFixed(1)}s</span>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              const updated = (plan.subtitles || []).filter(s => s.id !== seg.id);
                              updatePlanWithHistory({ ...plan, subtitles: updated });
                            }}
                            className="text-zinc-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Delete segment"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <p className="text-xs font-semibold text-zinc-900 leading-snug">
                          {seg.text}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* VISUAL INSERTS TAB (Stage 6) */}
            {activeTab === 'inserts' && (
              <div className="space-y-4">
                {/* Auto-Suggest Action Card */}
                <div className="p-3.5 bg-blue-500/10 border border-blue-200 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-blue-950 flex items-center gap-1.5">
                      <Layers className="w-4 h-4 text-blue-600" />
                      Contextual B-Roll Matching
                    </span>
                    <span className="text-[10px] font-mono bg-blue-200/60 text-blue-900 px-1.5 py-0.5 rounded font-semibold">
                      AI Timeline
                    </span>
                  </div>
                  <p className="text-[11px] text-blue-800 leading-relaxed">
                    Analyzes spoken keywords from your transcript and places matching uploaded photos as PiP or split overlays.
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAutoSuggestInserts}
                    disabled={!plan.subtitles || plan.subtitles.length === 0 || images.length === 0}
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center gap-1.5 shadow-xs"
                  >
                    <Wand2 className="w-3.5 h-3.5" />
                    <span>Auto-Match B-Roll from Speech</span>
                  </Button>
                </div>

                {/* Inserts List */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-900 block">
                    Active Visual Overlays ({plan.visual_inserts?.length || 0})
                  </label>
                  <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                    {(plan.visual_inserts || []).map(ins => (
                      <div
                        key={ins.id}
                        className="p-2.5 rounded-lg border border-zinc-200 bg-white hover:border-zinc-300 transition-colors space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-zinc-900 truncate max-w-[170px]">
                            {ins.label || 'Visual Overlay'}
                          </span>
                          <button
                            onClick={() => {
                              const updated = (plan.visual_inserts || []).filter(i => i.id !== ins.id);
                              updatePlanWithHistory({ ...plan, visual_inserts: updated });
                            }}
                            className="text-zinc-400 hover:text-red-500 transition-colors"
                            title="Remove insert"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>

                        <div className="flex items-center gap-2">
                          <img
                            src={getMediaUrl(ins.asset_url)}
                            alt=""
                            className="w-12 h-12 object-cover rounded border border-zinc-200"
                          />
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-1 text-[11px] text-zinc-500 font-mono">
                              <span>{ins.start_time.toFixed(1)}s</span>
                              <span>•</span>
                              <span>{ins.duration.toFixed(1)}s dur</span>
                            </div>

                            {/* Mode selector */}
                            <div className="flex items-center gap-1 text-[10px]">
                              {(['pip', 'split', 'cutaway'] as const).map(m => (
                                <button
                                  key={m}
                                  onClick={() => {
                                    const updated = (plan.visual_inserts || []).map(i =>
                                      i.id === ins.id ? { ...i, mode: m } : i
                                    );
                                    updatePlanWithHistory({ ...plan, visual_inserts: updated });
                                  }}
                                  className={`px-1.5 py-0.5 rounded uppercase font-semibold ${
                                    ins.mode === m
                                      ? 'bg-blue-600 text-white'
                                      : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'
                                  }`}
                                >
                                  {m}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </aside>

        {/* CENTER VIEWPORT: Video Preview & Playback Controls */}
        <main className="flex-1 min-h-0 min-w-0 flex flex-col bg-zinc-100 items-center gap-2 p-2 sm:p-4 overflow-hidden">
          {/* Top Info Bar */}
          <div className="w-full max-w-sm shrink-0 flex items-center justify-between text-xs text-zinc-500 font-mono pb-2">
            <span>PREVIEW</span>
            <span className="font-semibold text-zinc-800 uppercase">
              {plan.aspect_ratio} • {plan.fit_mode || 'fill'} • {plan.style}
            </span>
          </div>

          {/* Viewport Box */}
          <div data-testid="preview-area" style={{ containerType: 'size' }} className="relative flex-1 min-h-0 min-w-0 flex items-center justify-center w-full">
            <div
              style={{
                width: `min(100cqw, calc(100cqh * ${plan.aspect_ratio === '16:9' ? 16 / 9 : plan.aspect_ratio === '1:1' ? 1 : 9 / 16}))`,
                height: `min(100cqh, calc(100cqw / ${plan.aspect_ratio === '16:9' ? 16 / 9 : plan.aspect_ratio === '1:1' ? 1 : 9 / 16}))`
              }}
              className="relative rounded-xl overflow-hidden border border-zinc-300 bg-zinc-950 shrink-0"
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
                  onClick={() => { setIsPlaying(false); setViewRenderedVideo(!viewRenderedVideo); }}
                  className="absolute bottom-3 right-3 px-2.5 py-1 rounded bg-white text-zinc-900 text-[11px] font-medium shadow-md hover:bg-zinc-100 transition-colors border border-zinc-200"
                >
                  {viewRenderedVideo ? 'Canvas Mode' : 'Watch Exported MP4'}
                </button>
              )}
            </div>
          </div>

          {/* Playback Controller */}
          <div data-testid="playback-controls"
          className="w-full max-w-md shrink-0 p-2 rounded-xl bg-white border border-zinc-200 shadow-sm flex items-center justify-between gap-4">
            <button
              onClick={handleTogglePlay}
              className="w-9 h-9 rounded-full bg-zinc-900 hover:bg-zinc-800 text-white flex items-center justify-center transition-transform active:scale-95 shrink-0 shadow-sm"
              aria-label={isPlaying ? 'Pause' : 'Play'}
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
                aria-label="Playback position"
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
        <aside className={`${mobilePanel === 'director' ? 'flex absolute inset-y-0 right-0 z-30 shadow-xl' : 'hidden'} xl:static xl:flex w-80 max-w-[85vw] border-l border-zinc-200 bg-white flex-col shrink-0 overflow-hidden`}>
          <button className="xl:hidden text-xs p-2 border-b" onClick={() => setMobilePanel(null)}>Close director</button>
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

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-2 h-2 rounded-full ${
                    ollamaStatus.available ? 'bg-emerald-500 ring-2 ring-emerald-200' : 'bg-zinc-300'
                  }`}
                />
                <span className="text-[10px] font-mono text-zinc-500 truncate max-w-[125px]">
                  {ollamaStatus.available
                    ? `Ollama: ${selectedOllamaModel || 'Connected'}`
                    : 'Ollama: Offline (Fallback)'}
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-100 text-zinc-700 border border-zinc-200">
                AI DIRECTOR
              </span>
            </div>
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
                'Move the fifth photo to the beginning.',
                'Make the second image last three seconds.',
                'Add a fade-in between the second and third photos.',
                'Emphasize important words.',
                'Turn this talking-head video into a dynamic reel.',
                'Remove the eighth photo.',
                'Apply a crossfade between photos one and two.',
                'Change the video to landscape.'
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

      {/* Auto-Edit Talking-Head Reel Workflow Modal (Stage 7) */}
      {isAutoEditModalOpen && (
        <div className="fixed inset-0 z-50 bg-zinc-950/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-zinc-200 rounded-2xl max-w-md w-full p-6 shadow-xl space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-600">
                  <Wand2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-zinc-900">Auto Reel</h3>
                  <p className="text-[11px] text-zinc-500">Local AI transcription, expressive captions & B-roll</p>
                </div>
              </div>
              <button
                onClick={() => setIsAutoEditModalOpen(false)}
                className="text-zinc-400 hover:text-zinc-600 text-xs p-1"
              >
                ✕
              </button>
            </div>

            <label className="flex items-center gap-2 text-xs text-zinc-700">
              <input type="checkbox" checked={includeCaptions} onChange={e => setIncludeCaptions(e.target.checked)} />
              Generate captions from speech
            </label>
            <p className="text-xs text-zinc-500">Output: {plan.aspect_ratio}. Uses your uploaded photos or primary video.</p>
            {/* Choose Reel Style */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-zinc-800 block">
                Select Editing Style
              </label>
              <div className="space-y-2">
                {[
                  {
                    id: 'fitness_energy',
                    name: 'Fitness High Energy',
                    desc: 'Fast pacing, vibrant color grade, active word-by-word yellow pops & PiP overlays',
                    tag: 'Reels & TikTok'
                  },
                  {
                    id: 'minimalist',
                    name: 'Minimalist Clean',
                    desc: 'Clean letterbox fit, subtle crimson accents, full phrase captions & split screen',
                    tag: 'Educational & Podcasts'
                  },
                  {
                    id: 'cinematic',
                    name: 'Cinematic Story',
                    desc: 'Smooth slow-zoom motion, bold centered typography, and cinematic crossfades',
                    tag: 'Storytelling & Lifestyle'
                  }
                ].map(style => (
                  <button
                    key={style.id}
                    onClick={() => setAutoEditStyle(style.id as any)}
                    className={`w-full p-3 rounded-xl border text-left transition-all ${
                      autoEditStyle === style.id
                        ? 'border-zinc-900 bg-zinc-50 ring-1 ring-zinc-900 shadow-xs'
                        : 'border-zinc-200 bg-white hover:border-zinc-300'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-zinc-900">{style.name}</span>
                      <span className="text-[10px] font-mono text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded">
                        {style.tag}
                      </span>
                    </div>
                    <p className="text-[11px] text-zinc-500 leading-relaxed">
                      {style.desc}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-zinc-100">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsAutoEditModalOpen(false)}
                disabled={isAutoEditing}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleExecuteAutoEdit}
                disabled={isAutoEditing || images.length === 0}
                className="bg-zinc-900 hover:bg-zinc-800 text-white flex items-center gap-1.5"
              >
                {isAutoEditing ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Analyzing & Building Reel...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Generate Reel Draft</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StudioPage;
