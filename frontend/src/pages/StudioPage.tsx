import { syncPreviewMedia, releasePreviewMedia } from '../utils/previewMedia';
import { previewTimeline, transitionAt, frameAt, PREVIEW_FPS } from '../utils/previewTiming';
import { VoiceInputButton } from '../components/VoiceInputButton';
import { NumericInput } from '../components/ui/NumericInput';
import { useSharedReel } from '../services/useSharedReel';
import { editorRequest } from '../services/editorClient';
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
  generateAutoEditReel,
  generateTasteReel,
  getTasteProfile
} from '../services/api';
import { recalculateTimeline, uploadedClip } from '../utils/timeline';
import { getSettings } from '../services/settings';
import { InteractiveTimeline } from '../components/studio/InteractiveTimeline';
import { CreativePanel } from '../components/studio/CreativePanel';
import { useCreativePreview } from '../components/studio/useCreativePreview';
import { CaptionSettings } from '../components/studio/CaptionSettings';
import { CaptionTools } from '../components/studio/CaptionTools';
import { SpeechModelSelect } from '../components/studio/SpeechModelSelect';
import { useSpeechModels } from '../components/studio/useSpeechModels';
import { attachTranscript, editCaptionTiming, newCaptionInterval, mergeSourceCaptions } from '../utils/subtitles';
import { applyDirectorPlan, createDirectorPlan, creativeRequest } from '../services/api';
import { deleteCaptions, isEditingText } from '../utils/editorSelection';
import type { AIEditingPlan } from '../types';
import { EffectsPanel } from '../components/studio/EffectsPanel';
import { downloadTimeline, exportTimeline } from '../utils/timelineExport';
import {
  Mic,
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
  X,
} from 'lucide-react';

interface StudioPageProps {
  onBackToHome: () => void;
  feature?: string;
}

export const StudioPage: React.FC<StudioPageProps> = ({ onBackToHome, feature }) => {
  // Project State
  const [projectName, setProjectName] = useState('My Rayflow Reel');
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
  const [transcriptionSource, setTranscriptionSource] = useState('');
  const [transcriptionLanguage, setTranscriptionLanguage] = useState('');
  const [transcriptionStage, setTranscriptionStage] = useState('');
  const transcriptionJobRef = useRef<string | null>(null);

  const [directorConnection, setDirectorConnection] = useState({ label: 'AI connections', configured: false });

  // Auto-Edit Workflow Modal State
  const [isAutoEditModalOpen, setIsAutoEditModalOpen] = useState(false);
  const [autoEditStyle, setAutoEditStyle] = useState<'fitness_energy' | 'minimalist' | 'cinematic'>('cinematic');
  const [useTasteReel, setUseTasteReel] = useState(false);
  const [hasTasteProfile, setHasTasteProfile] = useState(false);
  const [tightenSpeech, setTightenSpeech] = useState(false);
  const [isAutoEditing, setIsAutoEditing] = useState(false);
  const [includeCaptions, setIncludeCaptions] = useState(true);
  const [autoStage, setAutoStage] = useState('');
  const [modelChoice, setWhisperModel] = useState('');
  const speechModels = useSpeechModels();
  const whisperModel = speechModels.catalog?.models.some(model => model.id === modelChoice && model.status === 'ready')
    ? modelChoice : speechModels.catalog?.default_model || '';
  const [seekVersion, setSeekVersion] = useState(0);
  const [mobilePanel, setMobilePanel] = useState<'media' | 'director' | null>(null);
  useEffect(() => {
    if (feature === 'captions') { setActiveTab('captions'); setMobilePanel('media'); }
    if (feature === 'auto-reel') setIsAutoEditModalOpen(true);
    if (feature === 'audio') { setActiveTab('music'); setMobilePanel('media'); }
  }, [feature]);

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
  const [selectedCaptionIds, setSelectedCaptionIds] = useState<string[]>([]);
  const [audioSelected, setAudioSelected] = useState(false);
  const selectClip = (id: string | null) => { setSelectedClipId(id); setSelectedCaptionIds([]); setAudioSelected(false); setSelectedTransitionId(null); };
  const selectCaption = (id: string, multiple = false) => {
    setSelectedCaptionIds(previous => multiple ? previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id] : [id]);
    setSelectedClipId(null); setSelectedTransitionId(null); setAudioSelected(false);
  };

  // Undo / Redo History
  type HistoryEntry = { plan: EditingPlan; audio: UploadedAudio | null; audioAnalysis: AudioAnalysisResult | null };
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [redoStack, setRedoStack] = useState<HistoryEntry[]>([]);
  const timelineRefreshIdRef = useRef(0);
  const editOriginRef = useRef<EditingPlan | null>(null);
  const planRef = useRef(plan);
  useLayoutEffect(() => { planRef.current = plan; }, [plan]);
  const pollTimersRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  // Assistant / Directing State
  const [commandInput, setCommandInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isInterpreting, setIsInterpreting] = useState(false);
  const [pendingAIPlan, setPendingAIPlan] = useState<AIEditingPlan | null>(null);
  const pendingOrigin = useRef<EditingPlan | null>(null);
  const directorBusy = useRef(false);
  const [directorStage, setDirectorStage] = useState('');
  const [directionTips, setDirectionTips] = useState(() => {
    try { return sessionStorage.getItem('rayflow:direction-tips-dismissed') !== 'true'; } catch { return true; }
  });
  const [conversation, setConversation] = useState<Array<{ sender: 'user' | 'assistant'; text: string; time: string }>>([
    {
      sender: 'assistant',
      text: 'Welcome to Rayflow AI. Bring in your footage and music, then tell me how the edit should feel. You can shape every cut, caption, and transition on the timeline.',
      time: 'Just now'
    }
  ]);

  // Video Preview & Playback State
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0.0);
  const currentTimeRef = useRef(0.0);
  const lastUiUpdateRef = useRef(0);
  const previewCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const transformCanvases = useRef<HTMLCanvasElement[]>([]);
  const synchronizedAudioRef = useRef<HTMLAudioElement | null>(null);
  const imageCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());
  const videoCacheRef = useRef<Map<string, HTMLVideoElement>>(new Map());
  const previewBackBufferRef = useRef<HTMLCanvasElement | null>(null);
  const drawFrameRef = useRef<(time: number) => void>(() => {});
  const playbackRef = useRef(false);
  useLayoutEffect(() => { playbackRef.current = isPlaying; }, [isPlaying]);
  useEffect(() => () => {
    pollTimersRef.current.forEach(clearInterval);
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

  const { render: renderCreative, captionRegions } = useCreativePreview(plan, isPlaying, seekVersion, currentTimeRef, drawFrameRef, setErrorMessage);

  const readOnly = useSharedReel({ projectName, images, audio, audioAnalysis, plan }, parsed => {
    setProjectName(parsed.projectName || 'My Rayflow Reel');
    setImages(parsed.images || []);
    setAudio(parsed.audio || null);
    setAudioAnalysis(parsed.audioAnalysis || null);
    if (parsed.plan) setPlan({ ...parsed.plan, fit_mode: parsed.plan.fit_mode || 'fill', transitions: parsed.plan.transitions || [] });
    setHistory([]); setRedoStack([]);
    setPendingAIPlan(null); pendingOrigin.current = null;
    setSelectedCaptionIds([]); setSelectedClipId(null); setSelectedTransitionId(null); setAudioSelected(false);
    setConversation([{ sender: 'assistant', text: 'Project loaded. Tell me what you want to change.', time: 'Just now' }]);
  }, setErrorMessage, hasHydrated, setHasHydrated);

  useEffect(() => {
    const insert = (event: Event) => {
      if (!window.location.hash.startsWith('#/studio')) return;
      const asset = (event as CustomEvent).detail;
      void editorRequest(`/editor/assets/${encodeURIComponent(asset.id)}/studio`, { method: 'POST' }).then(media => {
        if (media.media_type === 'audio') { setAudio(media); setAudioAnalysis(null); }
        else setImages(previous => previous.some(item => item.filename === media.filename) ? previous : [...previous, media]);
      }).catch(error => setErrorMessage(error.message));
    };
    window.addEventListener('rayflow:insert-asset', insert);
    return () => window.removeEventListener('rayflow:insert-asset', insert);
  }, []);

  // Push new plan to history
  const updatePlanWithHistory = (newPlan: EditingPlan, recordHistory = true) => {
    timelineRefreshIdRef.current++;
    setViewRenderedVideo(false);
    if (recordHistory) {
      const before = editOriginRef.current || planRef.current;
      if (JSON.stringify(before) !== JSON.stringify(newPlan)) {
        setHistory(prev => [...prev.slice(-25), { plan: before, audio, audioAnalysis }]);
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
    const current = { plan: planRef.current, audio, audioAnalysis };
    setRedoStack(prev => [current, ...prev]);
    setHistory(prev => prev.slice(0, -1));
    timelineRefreshIdRef.current++;
    editOriginRef.current = null;
    setViewRenderedVideo(false);
    planRef.current = previous.plan; setPlan(previous.plan); setAudio(previous.audio); setAudioAnalysis(previous.audioAnalysis);
    if (previous.plan.playhead_time !== undefined) { currentTimeRef.current = previous.plan.playhead_time; setCurrentTime(previous.plan.playhead_time); setSeekVersion(v => v + 1); }
  };

  const handleRedo = () => {
    if (redoStack.length === 0) return;
    const next = redoStack[0];
    const current = { plan: planRef.current, audio, audioAnalysis };
    setHistory(prev => [...prev, current]);
    setRedoStack(prev => prev.slice(1));
    timelineRefreshIdRef.current++;
    editOriginRef.current = null;
    setViewRenderedVideo(false);
    planRef.current = next.plan; setPlan(next.plan); setAudio(next.audio); setAudioAnalysis(next.audioAnalysis);
    if (next.plan.playhead_time !== undefined) { currentTimeRef.current = next.plan.playhead_time; setCurrentTime(next.plan.playhead_time); setSeekVersion(v => v + 1); }
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
          if (video) releasePreviewMedia(video);
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
        releasePreviewMedia(video); videoCacheRef.current.delete(key);
      }
    });
  }, [plan.clips, plan.visual_inserts]);

  const clipMedia = (clip: ClipConfig, time: number): HTMLImageElement | HTMLVideoElement | undefined => {
    if (clip.media_type !== 'video') return imageCacheRef.current.get(clip.image_url);
    const video = videoCacheRef.current.get(clip.id);
    if (!video) return;
    const target = (clip.source_start || 0) + Math.max(0, time - clip.start_time);
    const active = time >= clip.start_time && time < clip.start_time + clip.duration;
    const shouldPlay = active && playbackRef.current;
    video.muted = !active;
    video.volume = Math.max(0, Math.min(1, clip.volume ?? 1));
    if (!syncPreviewMedia(video, target, shouldPlay)) return;

    return video;
  };
  const mediaReady = (media?: HTMLImageElement | HTMLVideoElement) => media instanceof HTMLVideoElement
    ? media.readyState >= 2 && !media.seeking : Boolean(media?.complete && media.naturalWidth > 0);

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
          const clip = uploadedClip(item, start);
          start += clip.duration;
          return clip;
        });
        updatePlanWithHistory(recalculateTimeline([...planRef.current.clips, ...appended], planRef.current.transitions, planRef.current));
      } else await refreshTimeline(planRef.current, combined, audio);
      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `Added ${uploaded.length} media file${uploaded.length > 1 ? 's' : ''} to your Rayflow library. Timeline updated.`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Could not upload your photos or video. Try adding the files again.');
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
          text: 'Your Rayflow sample reel is ready: four photos and a soundtrack. Try trimming a clip, syncing the cuts, or adding a title.',
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
    if (!audio) return;
    const current = { plan: planRef.current, audio, audioAnalysis };
    setHistory(previous => [...previous.slice(-25), current]);
    setRedoStack([]);
    if (isAudioPreviewPlaying && mediaAudioRef.current) {
      mediaAudioRef.current.pause();
      setIsAudioPreviewPlaying(false);
    }
    setAudio(null);
    setAudioAnalysis(null);
    setAudioSelected(false);
    synchronizedAudioRef.current?.pause();
    setViewRenderedVideo(false);
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
    selectClip(null);
    const trans = (plan.transitions || []).find(t => t.from_clip_id === fromClipId && t.to_clip_id === toClipId);
    if (trans) {
      setSelectedTransitionId(trans.id);
    } else {
      setSelectedTransitionId(`boundary-${fromClipId}-${toClipId}`);
    }
    setActiveTab('effects');
    setMobilePanel('media');
  };

  // Reflect the Director's selected provider, independent of Auto Reel's local tools.
  useEffect(() => {
    let active = true;
    const refresh = () => { void getSettings().then(settings => {
      if (!active) return;
      const configured: Record<string, boolean> = { openai: settings.openai_configured, anthropic: settings.anthropic_configured, gemini: settings.gemini_configured, openrouter: settings.openrouter_configured, agentrouter: settings.agentrouter_configured };
      const id = settings.ai_provider === 'auto' ? Object.keys(configured).find(id => configured[id]) || '' : settings.ai_provider;
      const names: Record<string, string> = { openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'Google Gemini', openrouter: 'OpenRouter', agentrouter: 'Agent Router', ollama: 'Ollama', local: 'Local commands' };
      setDirectorConnection({ label: names[id] || 'Set up AI', configured: id === 'local' || id === 'ollama' || !!configured[id] });
    }).catch(() => {}); };
    refresh(); window.addEventListener('rayflow:providers', refresh); window.addEventListener('rayflow:director-settings', refresh);
    return () => { active = false; window.removeEventListener('rayflow:providers', refresh); window.removeEventListener('rayflow:director-settings', refresh); };
  }, []);

  // Speech-to-Text Transcription via local Faster-Whisper
  const handleAutoTranscribe = async () => {
    const speechSource = transcriptionSource || images.find(item => item.media_type === 'video')?.filename || audio?.filename;
    if (!speechSource) {
      setErrorMessage('Please upload speech audio or video first.');
      return;
    }
    setIsTranscribing(true);
    setTranscriptionProgress(0);
    setTranscriptionStage('Queued');
    setErrorMessage(null);
    try {
      const before = planRef.current;
      const jobId = await startTranscription(speechSource, whisperModel, transcriptionLanguage);
      transcriptionJobRef.current = jobId;
      setTranscriptionProgress(0);

      let checking = false;
      const stopPolling = () => { clearInterval(pollTimer); pollTimersRef.current.delete(pollTimer); };
      const pollTimer = setInterval(async () => {
        if (checking) return;
        checking = true;
        try {
          const job = await getTranscriptionStatus(jobId);
          if(transcriptionJobRef.current!==jobId){stopPolling();return;}
          setTranscriptionStage(`${job.stage || job.status}${job.language ? ` · ${job.language}` : ''}${job.device ? ` · ${job.device}/${job.compute_type}` : ''}${job.notice ? ` · ${job.notice}` : ''}`);
          if (job.status === 'processing') {
            setTranscriptionProgress(Math.round(job.progress || 50));
          } else if (job.status === 'completed') {
            stopPolling();
            setIsTranscribing(false);
            setTranscriptionProgress(100);
            transcriptionJobRef.current = null;
            if(planRef.current!==before){setErrorMessage('The project changed during transcription. Your edits were preserved; generate captions again to use the cached transcript.');return;}
            if (job.subtitles && job.subtitles.length > 0) {
              const subtitles = attachTranscript(job.subtitles,planRef.current,speechSource);
              if (!subtitles.length) { setErrorMessage('No speech falls inside this source’s current timeline range. Existing captions were retained.'); return; }
              const updatedPlan: EditingPlan = {
                ...planRef.current,
                subtitles: mergeSourceCaptions(planRef.current, subtitles, speechSource), transcript: subtitles,
                source_filename:speechSource,source_fingerprint:job.source_fingerprint,transcript_model:job.model,
              };
              updatePlanWithHistory(updatedPlan);
              setActiveTab('captions');
              setConversation(prev => [
                ...prev,
                {
                  sender: 'assistant',
                  text: `Local transcription generated ${subtitles.length} captions. ${subtitles.some(s=>s.words?.length) ? 'Recorded word timings are available.' : 'These captions use phrase-level timing.'}`,
                  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
              ]);
            } else setErrorMessage('No speech was detected in the selected source. Existing captions were retained.');
          } else if (job.status === 'failed' || job.status === 'cancelled') {
            stopPolling();
            setIsTranscribing(false);
            transcriptionJobRef.current = null;
            if(job.status==='failed')setErrorMessage(`Transcription failed: ${job.error || 'Unknown error'}`);
          }
        } catch (e: any) {
          stopPolling();
          setIsTranscribing(false);
          transcriptionJobRef.current = null;
          setErrorMessage(`Transcription status error: ${e.message}`);
        } finally {
          checking = false;
        }
      }, 1200);
      pollTimersRef.current.add(pollTimer);
    } catch (err: any) {
      setIsTranscribing(false);
      setErrorMessage(err.message || 'Failed to start local transcription.');
    }
  };

  // Detect whether a taste profile exists so we can offer the personalized reel.
  useEffect(() => {
    let cancelled = false;
    void getTasteProfile()
      .then(result => { if (!cancelled) setHasTasteProfile(!!result.exists); })
      .catch(() => { if (!cancelled) setHasTasteProfile(false); });
    return () => { cancelled = true; };
  }, []);

  // Automatic Talking-Head / Photo Reel Generation Workflow
  const handleExecuteAutoEdit = async () => {
    if (images.length === 0) {
      setErrorMessage('Add photos or video to start your Rayflow reel draft.');
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
      const before = planRef.current;
      const newPlan = useTasteReel
        ? await generateTasteReel(mediaTarget, assets, {
            whisperModel, includeCaptions, currentPlan: plan,
            autoBroll: plan.auto_broll !== false, listSounds: plan.list_sounds !== false,
            tightenSpeech,
          }, setAutoStage)
        : await generateAutoEditReel(mediaTarget, autoEditStyle, assets, whisperModel, plan.aspect_ratio, includeCaptions, plan, setAutoStage, tightenSpeech);
      if (planRef.current !== before) throw new Error('The project changed during Auto Reel. Your edits were preserved; run again to apply a fresh draft.');
      const tasteMeta = (newPlan as { taste?: { strategy?: { style_name?: string }; used_qloo?: boolean } }).taste;
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
          text: useTasteReel && tasteMeta
            ? `Personalized "${tasteMeta.strategy?.style_name || 'Taste'}" reel generated from your taste profile${tasteMeta.used_qloo ? ' using Qloo cultural intelligence' : ''}. Structured ${newPlan.clips.length} clips — fully editable.`
            : `Auto Reel draft generated! Applied "${autoEditStyle.replace('_', ' ').toUpperCase()}" style, synchronized ${newPlan.clips.length} clip cuts, and structured your timeline.`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Auto reel generation failed.');
    } finally {
      setIsAutoEditing(false);
    }
  };

  // Natural Language Command Execution
  const handleExecuteCommand = async (cmdToRun?: string) => {
    const cmd = cmdToRun || commandInput;
    if (!cmd.trim() || directorBusy.current || pendingAIPlan || readOnly) return;
    directorBusy.current = true;
    const origin = planRef.current;
    setIsInterpreting(true);
    setDirectorStage('Understanding your direction…');
    setErrorMessage(null);
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setConversation(prev => [...prev, { sender: 'user', text: cmd, time: timeStr }]);
    setCommandInput('');

    try {
      const preferredProvider = (await getSettings()).ai_provider;
      if (preferredProvider === 'ollama') setDirectorStage('Ollama is planning your edit. CPU inference can take a few minutes...');
      if (preferredProvider === 'local') {
        const result = await interpretNaturalCommand(cmd, origin);
        if (planRef.current !== origin) throw new Error('The project changed while interpreting. Please send your direction again.');
        updatePlanWithHistory(result.plan);
        setConversation(prev => [...prev, { sender: 'assistant', text: result.explanation, time: timeStr }]);
        return;
      }
      const aiPlan = await createDirectorPlan(cmd, origin, {
        selected_clip_id: selectedClipId, selected_caption_ids: selectedCaptionIds,
        playhead_time: currentTimeRef.current, can_undo: history.length > 0, can_redo: redoStack.length > 0,
      }, conversation.slice(-20).map(turn => ({ role: turn.sender, content: turn.text.slice(0, 4000) })));
      if (planRef.current !== origin) throw new Error('The project changed while planning. Please send your direction again.');
      if (aiPlan.clarification || !aiPlan.actions.length) {
        setConversation(prev => [...prev, { sender: 'assistant', text: aiPlan.clarification || aiPlan.explanation, time: timeStr }]);
      } else {
        pendingOrigin.current = origin;
        setPendingAIPlan(aiPlan);
        setConversation(prev => [...prev, { sender: 'assistant', text: `${aiPlan.explanation} Review the proposed changes below before applying them.`, time: timeStr }]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not interpret this direction. Check Connections.';
      setErrorMessage(message);
      setConversation(prev => [...prev, { sender: 'assistant', text: message, time: timeStr }]);
    } finally {
      directorBusy.current = false;
      setDirectorStage('');
      setIsInterpreting(false);
    }
  };

  const approveAIPlan = async () => {
    if (!pendingAIPlan || directorBusy.current || readOnly) return;
    directorBusy.current = true;
    setIsInterpreting(true);
    setDirectorStage('Applying your edit…');
    try {
      const origin = pendingOrigin.current;
      if (!origin || planRef.current !== origin) throw new Error('The project changed after this proposal. Send your direction again to use the current timeline.');
      const historyAction = pendingAIPlan.actions.find(action => action.type === 'undo' || action.type === 'redo');
      if (historyAction?.type === 'undo' && !history.length || historyAction?.type === 'redo' && !redoStack.length) throw new Error('There is no matching history change available.');
      const result = historyAction ? null : await applyDirectorPlan(pendingAIPlan, origin);
      if (planRef.current !== origin) throw new Error('The project changed while applying. No AI changes were applied; please try again.');
      if (historyAction?.type === 'undo') handleUndo();
      else if (historyAction?.type === 'redo') handleRedo();
      else if (result) updatePlanWithHistory(result.proposed_plan);
      setConversation(prev => [...prev, { sender: 'assistant', text: historyAction ? (historyAction.type === 'undo' ? 'Undid the last edit.' : 'Redid the last edit.') : result!.applied_changes.join(' '), time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The approved edit could not be applied.';
      setErrorMessage(message);
      setConversation(prev => [...prev, { sender: 'assistant', text: message, time: 'Now' }]);
    } finally {
      setPendingAIPlan(null); pendingOrigin.current = null;
      directorBusy.current = false; setDirectorStage('');
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

          if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
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
    const destination = ctx;
    const transformed = !!(clip.rotation || clip.offset_x || clip.offset_y);
    if (transformed) {
      if (!transformCanvases.current.length) transformCanvases.current = [document.createElement('canvas'), document.createElement('canvas')];
      const source = transformCanvases.current[0];
      source.width = w; source.height = h;
      ctx = source.getContext('2d')!;
    }
    ctx.save();
    ctx.globalAlpha = transformed ? 1 : Math.max(0, Math.min(1, alpha));
    if (transformed) { ctx.fillStyle = 'black'; ctx.fillRect(0, 0, w, h); }
    if (plan.style === 'cinematic') {
      const strength = plan.color_strength ?? 1;
      ctx.filter = `contrast(${1 + .1 * strength}) saturate(${1 + .15 * strength})`;
    }

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
    if (transformed) {
      const [source, rotated] = transformCanvases.current;
      rotated.width = w; rotated.height = h;
      const rotationContext = rotated.getContext('2d')!;
      rotationContext.fillStyle = 'black'; rotationContext.fillRect(0, 0, w, h);
      rotationContext.translate(w / 2, h / 2);
      rotationContext.rotate((clip.rotation || 0) * Math.PI / 180);
      rotationContext.drawImage(source, -w / 2, -h / 2);
      // Compose the black exposed borders and the shifted frame before fading.
      const sourceContext = source.getContext('2d')!;
      sourceContext.fillStyle = 'black'; sourceContext.fillRect(0, 0, w, h);
      sourceContext.drawImage(rotated, (clip.offset_x || 0) * w, (clip.offset_y || 0) * h);
      destination.save(); destination.globalAlpha = Math.max(0, Math.min(1, alpha));
      destination.drawImage(source, 0, 0); destination.restore();
    }
  };

  // Direct canvas render function decoupled from React rendering cycle
  const renderPreviewFrame = (time: number) => {
    const displayCanvas = previewCanvasRef.current;
    if (!displayCanvas) return;
    const canvas = previewBackBufferRef.current ||= document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const clips = previewTimeline(plan);
    const totalFrames = frameAt(plan.duration_seconds);
    // Presentation uses the export grid; editable source ranges stay precise.
    time = Math.max(0, Math.min(Math.floor(time * PREVIEW_FPS + 1e-7), totalFrames - 1)) / PREVIEW_FPS;
    const clipIdx = clips.findIndex(c => time >= c.start_time && time < c.start_time + c.duration);
    const activeClip = clips[clipIdx];
    const nextClip = clips[clipIdx + 1];
    const boundary = transitionAt(plan, clips, clipIdx);
    const cached = activeClip ? clipMedia(activeClip, time) : undefined;
    // Warm the next occurrence at its source-in even for hard cuts.
    const nextCached = nextClip ? clipMedia(nextClip, time) : undefined;
    const inTransition = !!(activeClip && boundary && time >= activeClip.start_time + activeClip.duration - boundary.duration);
    videoCacheRef.current.forEach((video, id) => {
      if (id !== activeClip?.id) video.pause();
    });
    // Do not clear/publish a partial composition while a decoder is seeking.
    if (activeClip && (!mediaReady(cached) || (inTransition && !mediaReady(nextCached)))) return;

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

    if (activeClip && activeClip.image_url) {
      if (cached && mediaReady(cached)) {
        const clipProgress = activeClip.duration > 0
          ? Math.min(1, Math.max(0, (time - activeClip.start_time) / Math.max(1 / PREVIEW_FPS, activeClip.duration - 1 / PREVIEW_FPS)))
          : 0;

        // Check if a transition is active with the next clip
        let transitionHandled = false;
        if (nextClip) {
          const boundaryTrans = boundary;
          if (boundaryTrans) {
            const tDur = boundaryTrans.duration;
            const clipEnd = activeClip.start_time + activeClip.duration;
            const tStart = clipEnd - tDur;

            if (time >= tStart && time < clipEnd) {
              const transProgress = (time - tStart) / tDur;

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

        if (renderCreative(ctx, time, w, h) === false) return;

      } else {
        // Drawing placeholder while image decodes
        ctx.fillStyle = '#151f22';
        ctx.fillRect(0, 0, w, h);
        ctx.textAlign = 'center';
        ctx.font = `500 ${Math.max(14, Math.round(Math.min(w, h) * .045))}px Onest, sans-serif`;
        ctx.fillStyle = '#aebdb3';
        ctx.fillText('Preparing your clip preview…', w / 2, h / 2);
      }
    } else {
      // Clean empty state
      ctx.fillStyle = '#0d1417';
      ctx.fillRect(0, 0, w, h);
      ctx.textAlign = 'center';
      ctx.font = `500 ${Math.max(14, Math.round(Math.min(w, h) * .045))}px Onest, sans-serif`;
      ctx.fillStyle = '#dfe7e0';
      ctx.fillText('Your Rayflow preview', w / 2, h / 2 - Math.min(w, h) * .02);
      ctx.font = `400 ${Math.max(12, Math.round(Math.min(w, h) * .035))}px Onest, sans-serif`;
      ctx.fillStyle = '#aebdb3';
      ctx.fillText('Add photos or video to see your edit', w / 2, h / 2 + Math.min(w, h) * .04);
    }
    if (displayCanvas.width !== w || displayCanvas.height !== h) {
      displayCanvas.width = w; displayCanvas.height = h;
    }
    displayCanvas.getContext('2d')?.drawImage(canvas, 0, 0);
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
      const plan = planRef.current;
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
        if (synchronizedAudioRef.current) synchronizedAudioRef.current.volume = (plan.clips.some(c => c.media_type === 'video') ? (plan.music_volume ?? .25) : 1) * Math.max(0, Math.min(1, (plan.duration_seconds - next) / Math.min(1.5, plan.duration_seconds)));

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
  }, [isPlaying]);

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
    setSeekVersion(version => version + 1);
    newTime = Math.max(0, Math.min(plan.duration_seconds, newTime));
    setViewRenderedVideo(false);
    currentTimeRef.current = newTime;
    setCurrentTime(newTime);
    if (synchronizedAudioRef.current && audio) {
      synchronizedAudioRef.current.currentTime = newTime;
    }
    renderPreviewFrame(newTime);
  };

  useLayoutEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || isEditingText(event.target) || readOnly || pendingAIPlan || isAutoEditModalOpen || isRenderingModalOpen) return;
      const element = event.target instanceof Element ? event.target : null;
      if (element && element !== document.body && !element.closest('.rayflow-studio')) return;
      if (element?.closest('[role="dialog"], .rayflow-modal-backdrop') || document.querySelector('[role="dialog"]')) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey) handleRedo(); else handleUndo();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
        event.preventDefault(); handleRedo();
      } else if (!event.ctrlKey && !event.metaKey && !event.altKey && (event.key === 'Delete' || event.key === 'Backspace')) {
        if (event.repeat) return;
        if (selectedCaptionIds.length) {
          event.preventDefault();
          updatePlanWithHistory(deleteCaptions(planRef.current, selectedCaptionIds));
          setSelectedCaptionIds([]);
        } else if (audioSelected && audio) {
          event.preventDefault(); handleRemoveAudio();
        } else if (selectedClipId && planRef.current.clips.some(clip => clip.id === selectedClipId)) {
          event.preventDefault();
          updatePlanWithHistory(recalculateTimeline(planRef.current.clips.filter(clip => clip.id !== selectedClipId), planRef.current.transitions, planRef.current));
          selectClip(null);
        }
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
    if (originals.some(clip => clip.media_type === 'video')) {
      const clips = originals.map(clip => clip.media_type === 'video' || keepDuration
        ? clip : { ...clip, duration: seconds });
      updatePlanWithHistory(recalculateTimeline(clips, updated.transitions, updated));
      return;
    }
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

  if (!hasHydrated) return <main className="workspace-page" role="status" aria-busy="true">Opening your Studio project…</main>;

  return (
    <div className="rayflow-studio flex flex-col h-dvh bg-studio-canvas text-studio-text select-none overflow-hidden">
      {readOnly && <div role="status" className="p-2 text-sm">Viewer access. Changes in this preview are temporary. Download and import a project copy to save your own edits.</div>}
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
      {feature === 'export' && <div className="p-3 text-xs bg-studio-panel border-b border-studio-border" role="status">Timeline export includes cut timing, source trims and media references. Use Export timeline in the toolbar. Captions, grading and transitions are saved as Rayflow metadata; use Render for their final appearance.</div>}
      <header className="h-14 gap-4 overflow-x-auto border-b border-studio-border bg-studio-panel px-3 flex items-center justify-between z-30 shrink-0">
        {/* Left: Back & Project Name */}
        <div className="flex items-center gap-3">
          <button
            onClick={onBackToHome}
            className="p-1.5 rounded-lg text-studio-muted hover:text-studio-text hover:bg-studio-hover transition-colors"
            title="Return to Landing Page"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>

          <div className="h-4 w-px bg-studio-line" />
          <a href="#/connections" className="text-xs text-studio-muted">Connections</a>
          <a href="#/dashboard" className="text-xs text-studio-muted">Dashboard</a>
          <button className="text-xs text-studio-muted whitespace-nowrap" onClick={() => {
            try { downloadTimeline(exportTimeline(plan, projectName, audio, value => new URL(getMediaUrl(value), window.location.origin).href), projectName); }
            catch (error) { setErrorMessage(error instanceof Error ? error.message : 'Timeline export failed.'); }
          }}>Export timeline</button>

          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent" />
            <input
              type="text"
              value={projectName}
              onChange={e => setProjectName(e.target.value)}
              className="w-28 text-sm font-semibold text-studio-text bg-transparent border-b border-transparent hover:border-studio-border focus:border-accent focus:outline-none transition-colors px-1"
              title="Click to rename project"
            />
          </div>
        </div>

        {/* Center: Aspect Ratio & Image Fit Mode Controls */}
        <div className="flex shrink-0 items-center gap-3">
          {/* Aspect Ratio Selector */}
          <div className="flex items-center p-0.5 bg-studio-hover rounded-lg border border-studio-border shadow-2xs">
            <button
              onClick={() => updatePlanWithHistory({ ...plan, aspect_ratio: '9:16' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                plan.aspect_ratio === '9:16'
                  ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                  : 'text-studio-muted hover:text-studio-text'
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
                  ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                  : 'text-studio-muted hover:text-studio-text'
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
                  ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                  : 'text-studio-muted hover:text-studio-text'
              }`}
              title="1:1 Square (1080×1080) for Instagram Feed"
            >
              <Square className="w-3.5 h-3.5" />
              <span>1:1</span>
            </button>
          </div>

          <div className="h-4 w-px bg-studio-line" />

          {/* Fit Mode Toggle */}
          <div className="flex items-center p-0.5 bg-studio-hover rounded-lg border border-studio-border shadow-2xs">
            <button
              onClick={() => updatePlanWithHistory({ ...plan, fit_mode: 'fill' })}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                (plan.fit_mode || 'fill') === 'fill'
                  ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                  : 'text-studio-muted hover:text-studio-text'
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
                  ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                  : 'text-studio-muted hover:text-studio-text'
              }`}
              title="Fit to Frame (preserve the full photo or video)"
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
              className="p-1.5 rounded-lg text-studio-muted hover:text-studio-text hover:bg-studio-hover disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Undo2 className="w-4 h-4" />
            </button>
            <button
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              className="p-1.5 rounded-lg text-studio-muted hover:text-studio-text hover:bg-studio-hover disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Redo"
            >
              <Redo2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                if (window.confirm('Reset this project to start fresh?')) {
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
              className="p-1.5 rounded-lg text-studio-muted hover:text-studio-text hover:bg-studio-hover text-xs transition-colors"
              title="New / Clear Project"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-4 w-px bg-studio-line" />

          <Button
            variant="secondary"
            size="sm"
            onClick={() => setIsAutoEditModalOpen(true)}
            className="flex items-center gap-1.5 border-brass-border hover:border-brass-border bg-brass-soft/50 hover:bg-brass-soft/60 text-brass"
            title="Create a Rayflow draft with speech captions and contextual B-roll"
          >
            <Wand2 className="w-3.5 h-3.5 text-brass" />
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
        <div role="alert" className="shrink-0 max-h-20 overflow-auto border-b border-studio-border px-3 py-2 text-xs bg-studio-panel flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /><span className="flex-1">{errorMessage}</span>
          <button aria-label="Dismiss message" onClick={() => setErrorMessage(null)}>Dismiss</button>
        </div>
      )}
      {/* Main Studio Area (3 Columns: Left Media/Settings, Center Preview, Right AI Assistant) */}
      <div className="flex-1 min-h-0 flex relative overflow-hidden">
        {/* LEFT PANEL: Media Library & Settings */}
        <aside className={`${mobilePanel === 'media' ? 'flex absolute inset-y-0 left-0 z-30 shadow-xl' : 'hidden'} lg:static lg:flex w-72 max-w-[85vw] border-r border-studio-border bg-studio-raised flex-col shrink-0 overflow-hidden`}>
          <button className="lg:hidden text-xs p-2 border-b" onClick={() => setMobilePanel(null)}>Close media</button>
          {/* Tabs */}
          <div className="flex border-b border-studio-border bg-studio-panel px-2 pt-2 gap-1 text-xs font-medium overflow-x-auto">
            <button
              onClick={() => setActiveTab('photos')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'photos'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
              }`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Media ({images.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('music')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'music'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
              }`}
            >
              <Music className="w-3.5 h-3.5" />
              <span>Music {audio ? '•' : ''}</span>
            </button>

            <button
              onClick={() => setActiveTab('captions')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'captions'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
              }`}
              title="Style and time your speech captions"
            >
              <Subtitles className="w-3.5 h-3.5 text-brass" />
              <span>Captions {plan.subtitles && plan.subtitles.length > 0 ? `(${plan.subtitles.length})` : ''}</span>
            </button>

            <button
              onClick={() => setActiveTab('inserts')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'inserts'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
              }`}
              title="Layer B-roll and visual inserts into your edit"
            >
              <Layers className="w-3.5 h-3.5 text-jade" />
              <span>Inserts {plan.visual_inserts && plan.visual_inserts.length > 0 ? `(${plan.visual_inserts.length})` : ''}</span>
            </button>

            <button
              onClick={() => setActiveTab('effects')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'effects'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Effects</span>
            </button>

            <button
              onClick={() => setActiveTab('style')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'style'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Pacing</span>
            </button>

            <button
              onClick={() => setActiveTab('title')}
              className={`px-3 py-2 rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 shrink-0 ${
                activeTab === 'title'
                  ? 'border-accent text-studio-text font-semibold bg-studio-raised'
                  : 'border-transparent text-studio-muted hover:text-studio-text'
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
                  className="border border-dashed border-studio-border hover:border-studio-border bg-studio-panel rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer transition-colors text-center group shadow-sm"
                >
                  <Upload className="w-5 h-5 text-studio-muted mb-1.5 group-hover:text-studio-text transition-colors" />
                  <span className="text-xs font-semibold text-studio-text">
                    Bring your footage
                  </span>
                  <span className="text-[11px] text-studio-muted mt-0.5">
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
                  <div className="flex items-center justify-center gap-2 py-2 text-xs text-studio-text bg-studio-hover rounded-lg">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Adding footage to Rayflow…</span>
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleLoadDemoProject}
                  disabled={isUploading}
                  className="w-full py-2 px-3 rounded-lg border border-studio-border bg-studio-panel hover:bg-studio-raised hover:border-studio-border transition-colors text-xs font-medium text-studio-text flex items-center justify-center gap-2 shadow-2xs"
                  title="Explore Rayflow with four sample photos and a soundtrack"
                >
                  <Sparkles className="w-3.5 h-3.5 text-studio-muted" />
                  <span>Try a Rayflow sample reel</span>
                </button>


                {images.length === 0 ? (
                  <div className="text-center py-10 px-4 text-xs text-studio-muted border border-studio-border rounded-xl bg-studio-panel space-y-2">
                    <p className="font-medium text-studio-text">Your story starts here</p>
                    <p className="text-[11px]">Add photos or video to begin your Rayflow edit.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-studio-muted px-1">
                      <span>{images.length} media files ready</span>
                      <button
                        onClick={() => {
                          setImages([]);
                          refreshTimeline(plan, [], audio);
                        }}
                        className="text-studio-muted hover:text-danger transition-colors"
                      >
                        Clear All
                      </button>
                    </div>

                    {images.map((img, idx) => (
                      <div
                        key={img.filename + idx}
                        className="flex items-center justify-between p-2.5 rounded-lg bg-studio-panel border border-studio-border hover:border-studio-border transition-all shadow-sm"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {img.media_type === 'video'
                            ? <video src={getMediaUrl(img.url)} muted preload="metadata" className="w-10 h-10 object-cover rounded shrink-0" />
                            : <img src={getMediaUrl(img.url)} alt="" className="w-10 h-10 object-cover rounded shrink-0" />}
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-studio-text truncate">
                              {img.original_name}
                            </p>
                            <p className="text-[10px] text-studio-muted font-mono">
                              {(img.size / 1024).toFixed(0)} KB • {img.media_type === 'video' ? 'Video' : 'Photo'} #{idx + 1}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-0.5 shrink-0">
                          <button
                            onClick={() => handleMoveImage(idx, 'up')}
                            disabled={idx === 0}
                            className="p-1 text-studio-quiet hover:text-studio-text disabled:opacity-20"
                            title="Move Up"
                          >
                            <ArrowUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleMoveImage(idx, 'down')}
                            disabled={idx === images.length - 1}
                            className="p-1 text-studio-quiet hover:text-studio-text disabled:opacity-20"
                            title="Move Down"
                          >
                            <ArrowDown className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleRemoveImage(idx)}
                            className="p-1 text-studio-quiet hover:text-danger transition-colors"
                            title={img.media_type === 'video' ? 'Remove Video' : 'Remove Photo'}
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
                <label className="border border-dashed border-studio-border hover:border-studio-border bg-studio-panel rounded-xl p-5 flex flex-col items-center justify-center cursor-pointer transition-colors text-center group shadow-sm">
                  <Music className="w-5 h-5 text-studio-muted mb-1.5 group-hover:text-studio-text transition-colors" />
                  <span className="text-xs font-semibold text-studio-text">
                    {audio ? 'Replace Soundtrack' : 'Add Soundtrack'}
                  </span>
                  <span className="text-[11px] text-studio-muted mt-0.5">
                    Find the rhythm for your cuts with Librosa (MP3, WAV)
                  </span>
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleAudioUpload}
                    className="hidden"
                  />
                </label>

                {isAnalyzingAudio && (
                  <div className="flex items-center justify-center gap-2 py-2 text-xs text-studio-text bg-studio-hover rounded-lg">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Finding soundtrack beats with Librosa…</span>
                  </div>
                )}

                {audio ? (
                  <div className="p-3.5 rounded-xl bg-studio-panel border border-studio-border shadow-sm space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <button
                          onClick={handleToggleAudioPreview}
                          className="w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center hover:bg-accent-hover transition-colors shrink-0 shadow-2xs"
                        >
                          {isAudioPreviewPlaying ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                        </button>
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-studio-text truncate">
                            {audio.original_name}
                          </p>
                          <p className="text-[10px] text-studio-muted font-mono">
                            {(audio.size / (1024 * 1024)).toFixed(1)} MB
                          </p>
                        </div>
                      </div>

                      <button
                        onClick={handleRemoveAudio}
                        className="p-1 text-studio-quiet hover:text-danger transition-colors"
                        title="Remove Soundtrack"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {audioAnalysis && (
                      <div className="pt-2 border-t border-studio-line grid grid-cols-2 gap-2 text-center">
                        <div className="bg-studio-raised p-2 rounded-lg border border-studio-border">
                          <span className="text-[10px] text-studio-muted block">Tempo</span>
                          <span className="text-xs font-semibold font-mono text-studio-text">
                            {audioAnalysis.tempo} BPM
                          </span>
                        </div>
                        <div className="bg-studio-raised p-2 rounded-lg border border-studio-border">
                          <span className="text-[10px] text-studio-muted block">Beats Detected</span>
                          <span className="text-xs font-semibold font-mono text-studio-text">
                            {audioAnalysis.beat_count} Hits
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-10 px-4 text-xs text-studio-muted border border-studio-border rounded-xl bg-studio-panel space-y-2">
                    <p className="font-medium text-studio-text">No soundtrack selected</p>
                    <p className="text-[11px]">Give Rayflow a soundtrack to guide the rhythm of your cuts.</p>
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
                onSelectTransition={id => { selectClip(null); setSelectedTransitionId(id); }}
              />
            )}

            {/* PACING & STYLE TAB */}
            {activeTab === 'style' && (
              <div className="space-y-4">
                {/* Beat Sync Toggle */}
                <div className="flex items-center justify-between p-3 rounded-lg bg-studio-panel border border-studio-border shadow-sm">
                  <div>
                    <span className="text-xs font-semibold text-studio-text block">
                      Sync cuts to music
                    </span>
                    <span className="text-[11px] text-studio-muted">
                    Align your cuts with the soundtrack beats
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
                    className="w-4 h-4 accent-accent rounded cursor-pointer"
                  />
                </div>

                {/* Style Presets */}
                <div>
                  <label className="text-xs font-medium text-studio-text block mb-2">
                    Color and mood
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
                            ? 'border-accent bg-studio-panel ring-1 ring-accent shadow-sm'
                            : 'border-studio-border bg-studio-panel hover:border-studio-border'
                        }`}
                      >
                        <span className="text-xs font-semibold text-studio-text block">
                          {preset.label}
                        </span>
                        <span className="text-[10px] text-studio-muted">
                          {preset.desc}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {plan.style === 'cinematic' && <label className="block text-xs text-studio-text">Cinematic color strength
                  <NumericInput aria-label="Cinematic color strength" className="w-full rounded border p-1 mt-1" min={0} max={100}
                    value={Math.round((plan.color_strength ?? 1)*100)} onCommit={value=>updatePlanWithHistory({...plan,color_strength:value/100})}/>
                  <span className="text-[10px] text-studio-muted">0 preserves source color. Auto Reel starts at 30 for gentle contrast.</span>
                </label>}
                {/* Pacing Speed */}
                <div>
                  <label className="text-xs font-medium text-studio-text block mb-2">
                    Cut pacing
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
                            ? 'border-accent bg-accent text-white shadow-sm'
                            : 'border-studio-border bg-studio-panel text-studio-text hover:border-studio-border'
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Duration Slider */}
                <div className="p-3 rounded-lg bg-studio-panel border border-studio-border shadow-sm space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-medium text-studio-text">Reel duration</span>
                    <span className="text-xs font-mono font-semibold text-studio-text">
                      {plan.duration_seconds.toFixed(1)}s
                    </span>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max={Math.max(60, Math.ceil(plan.duration_seconds))}
                    step="0.5"
                    value={plan.duration_seconds}
                    onChange={e => {
                      resizeDuration(parseFloat(e.target.value));
                    }}
                    className="w-full accent-accent cursor-pointer"
                  />
                </div>
              </div>
            )}

            {/* TITLE TAB */}
            {activeTab === 'title' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 rounded-lg bg-studio-panel border border-studio-border shadow-sm">
                  <div>
                    <span className="text-xs font-semibold text-studio-text block">
                      Show opening title
                    </span>
                    <span className="text-[11px] text-studio-muted">
                      Introduce your reel with a title
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
                    className="w-4 h-4 accent-accent rounded cursor-pointer"
                  />
                </div>

                {plan.title.enabled && (
                  <div className="space-y-3 pt-1">
                    <div>
                      <label className="text-xs font-medium text-studio-text block mb-1">
                        Opening title
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
                        placeholder="e.g. A STORY IN MOTION"
                        className="w-full bg-studio-panel border border-studio-border rounded-lg px-3 py-2 text-xs font-semibold text-studio-text outline-none focus:border-accent shadow-sm"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-studio-text block mb-1">
                        Supporting line (optional)
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
                        placeholder="e.g. Directed with Rayflow"
                        className="w-full bg-studio-panel border border-studio-border rounded-lg px-3 py-2 text-xs text-studio-text outline-none focus:border-accent shadow-sm"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* CAPTIONS TAB (Stage 4) */}
            {activeTab === 'captions' && (
              <div className="space-y-4">
                <div className="space-y-2 text-xs text-studio-text">
                  <label>Speech source<select aria-label="Transcription source" className="w-full border rounded p-1" value={transcriptionSource} onChange={e=>setTranscriptionSource(e.target.value)}>
                    <option value="">First video, or uploaded audio</option>
                    {images.filter(item=>item.media_type==='video').map(item=><option key={item.filename} value={item.filename}>{item.original_name}</option>)}
                    {audio && <option value={audio.filename}>{audio.original_name}</option>}
                  </select></label>
                  <SpeechModelSelect state={speechModels} value={whisperModel} onChange={setWhisperModel} label="Caption transcription model" />
                  <label>Language<input aria-label="Transcription language" list="caption-languages" className="w-full border rounded p-1" placeholder="Auto-detect, or a language code" value={transcriptionLanguage} onChange={e=>setTranscriptionLanguage(e.target.value)} /></label>
                  <datalist id="caption-languages">{[['en','English'],['hi','Hindi'],['mr','Marathi'],['te','Telugu'],['kn','Kannada'],['ta','Tamil'],['ml','Malayalam'],['bn','Bengali'],['gu','Gujarati'],['pa','Punjabi'],['ne','Nepali'],['ur','Urdu'],['es','Spanish'],['fr','French'],['de','German'],['ja','Japanese']].map(([code,name])=><option key={code} value={code}>{name}</option>)}</datalist>
                  <p className="text-studio-muted">Leave language empty for mixed speech. Processing is local and free after the selected model is cached. Regeneration keeps manual captions and captions from other sources.</p>
                  {transcriptionStage && <p role="status" aria-live="polite">{transcriptionStage}{isTranscribing ? ` · ${transcriptionProgress}%` : ''}</p>}
                  {isTranscribing && <button className="border rounded px-2 py-1" onClick={()=>{if(transcriptionJobRef.current)void creativeRequest('/transcribe/'+transcriptionJobRef.current+'/cancel',{}).catch(error=>setErrorMessage(error.message));}}>Cancel transcription</button>}
                </div>
                <CaptionSettings plan={plan} onChange={updatePlanWithHistory} />
                <CaptionTools plan={plan} source={transcriptionSource || images.find(item => item.media_type === 'video')?.filename || audio?.filename} onChange={updatePlanWithHistory} />

                {/* Auto-Transcribe Action Card */}
                <div className="p-3.5 bg-brass/10 border border-brass-border rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-brass flex items-center gap-1.5">
                      <Subtitles className="w-4 h-4 text-brass" />
                    Turn speech into captions
                    </span>
                    <span className="text-[10px] font-mono bg-brass-soft/60 text-brass px-1.5 py-0.5 rounded font-semibold">
                      Faster-Whisper
                    </span>
                  </div>
                  <p className="text-[11px] text-brass leading-relaxed">
                    Create editable captions from your speech. Use word timings to follow the speaker and highlight key phrases.
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAutoTranscribe}
                    disabled={isTranscribing || !whisperModel || (!audio && !images.some(item => item.media_type === 'video'))}
                    className="w-full bg-accent hover:bg-accent-hover text-white flex items-center justify-center gap-1.5 shadow-xs"
                  >
                    {isTranscribing ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Transcribing... {transcriptionProgress}%</span>
                      </>
                    ) : (
                      <>
                        <Mic className="w-3.5 h-3.5" />
                        <span>Generate speech captions</span>
                      </>
                    )}
                  </Button>
                </div>

                {/* Caption Presets */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-studio-text block">
                    Caption style
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'cinematic', name: 'Cinematic', color: '#E7C48C', desc: 'Warm emphasis and balanced phrase captions' },
                      { id: 'bold_pop', name: 'Bold Pop', color: '#FACC15', desc: 'One word at a time, with yellow emphasis' },
                      { id: 'fitness_energy', name: 'Fitness Energy', color: '#38BDF8', desc: 'Cyan emphasis for energetic speech' },
                      { id: 'minimalist', name: 'Minimalist Clean', color: '#E11D48', desc: 'Quiet phrase captions with crimson emphasis' },
                      { id: 'subtle_border', name: 'Subtle Border', color: '#10B981', desc: 'Outlined phrases with emerald emphasis' },
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
                              words:s.words?.map(w=>({...w,color:undefined})),
                              style: {
                                ...(s.style || {
                                  preset: 'bold_pop' as SubtitlePreset,
                                  font_size: 72,
                                  font_family: 'Noto Sans',
                                  color: '#FFFFFF',
                                  highlight_color: '#FACC15',
                                  stroke_color: '#000000',
                                  stroke_width: 4,
                                  position: 'center_bottom' as const
                                }),
                                preset: preset.id as SubtitlePreset,
                                highlight_color: preset.color,
                                caption_mode: ['cinematic', 'minimalist', 'subtle_border'].includes(preset.id) ? 'phrase' as const : 'word_by_word' as const
                              }
                            }));
                            updatePlanWithHistory({ ...plan, subtitles: updatedSubs });
                          }}
                          className={`p-2.5 rounded-xl border text-left transition-all ${
                            isSelected
                              ? 'bg-accent text-white border-accent shadow-sm ring-1 ring-accent'
                              : 'bg-studio-panel text-studio-text border-studio-border hover:border-studio-border'
                          }`}
                        >
                          <div className="flex items-center gap-1.5 mb-1">
                            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: preset.color }} />
                            <span className="text-xs font-semibold">{preset.name}</span>
                          </div>
                          <p className={`text-[10px] leading-tight ${isSelected ? 'text-white' : 'text-studio-muted'}`}>
                            {preset.desc}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Caption Mode Switcher */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-studio-text block">
                    Caption timing
                  </label>
                  <div className="grid grid-cols-2 gap-2 p-1 bg-studio-hover rounded-lg border border-studio-border">
                    <button
                      onClick={() => {
                        if (!plan.subtitles) return;
                        const updated = plan.subtitles.map(s => ({
                          ...s,
                          style: { ...(s.style || {
                            preset: 'bold_pop' as SubtitlePreset,
                            font_size: 72,
                            font_family: 'Noto Sans',
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
                          ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                          : 'text-studio-muted hover:text-studio-text'
                      }`}
                    >
                      One word at a time
                    </button>
                    <button
                      onClick={() => {
                        if (!plan.subtitles) return;
                        const updated = plan.subtitles.map(s => ({
                          ...s,
                          style: { ...(s.style || {
                            preset: 'bold_pop' as SubtitlePreset,
                            font_size: 72,
                            font_family: 'Noto Sans',
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
                          ? 'bg-studio-panel text-studio-text font-semibold shadow-xs'
                          : 'text-studio-muted hover:text-studio-text'
                      }`}
                    >
                      Full phrases
                    </button>
                  </div>
                </div>

                {/* Subtitle Segments List */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-studio-text">
                      Your captions ({plan.subtitles?.length || 0})
                    </label>
                    <button
                      onClick={() => {
                        const interval=newCaptionInterval(plan,currentTime);
                        if(!interval){setErrorMessage('Choose an uncaptioned part of the timeline to add a caption.');return;}
                        const newSub: SubtitleSegment = {
                          id: crypto.randomUUID(),
                          text: 'NEW CAPTION PHRASE',
                          ...interval,
                          words: [], origin:'manual',
                        };
                        updatePlanWithHistory({
                          ...plan,
                          subtitles: [...(plan.subtitles || []), newSub]
                        });
                      }}
                      className="text-[11px] font-semibold text-brass hover:text-brass"
                    >
                      + Add caption
                    </button>
                  </div>

                  <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                    {(plan.subtitles || []).map(seg => (
                      <div
                        key={seg.id}
                        tabIndex={0}
                        data-caption-card={seg.id}
                        onKeyDown={event => { if (event.target === event.currentTarget && (event.key === ' ' || event.key === 'Enter')) { event.preventDefault(); selectCaption(seg.id, event.shiftKey || event.ctrlKey || event.metaKey); } }}
                        onClick={event => {
                          if (!isEditingText(event.target)) { selectCaption(seg.id, event.shiftKey || event.ctrlKey || event.metaKey); handleSeek(seg.start_time); }
                        }}
                        className={`p-2.5 rounded-lg border ${selectedCaptionIds.includes(seg.id) ? 'border-accent' : 'border-studio-border'} bg-studio-panel transition-colors cursor-pointer group`}
                      >
                        <div className="flex items-center justify-between text-[11px] text-studio-quiet font-mono mb-1">
                          <span>{seg.start_time.toFixed(1)}s - {seg.end_time.toFixed(1)}s</span>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              updatePlanWithHistory(deleteCaptions(planRef.current, [seg.id]));
                              setSelectedCaptionIds(ids => ids.filter(id => id !== seg.id));
                            }}
                            className="text-studio-quiet hover:text-danger opacity-70 group-hover:opacity-100 focus:opacity-100 transition-opacity"
                            title="Delete caption"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <textarea aria-label="Caption text" key={seg.id + seg.text} defaultValue={seg.text}
                          className="w-full border rounded p-1.5 text-xs text-studio-text" onBlur={e => {
                            if(e.target.value===seg.text)return;
                            const tokens=e.target.value.trim().split(/\s+/);
                            updatePlanWithHistory({...plan,subtitles:plan.subtitles?.map(s=>s.id===seg.id?{...s,text:e.target.value,origin:'manual',
                              words:tokens.length===s.words?.length?s.words.map((word,index)=>({...word,word:tokens[index]})):[]}:s)});
                          }} />

                        {!!seg.words?.length && <div className="flex flex-wrap gap-1" aria-label="Word emphasis">
                          {seg.words.map((word,index)=><button key={index} aria-pressed={!!word.emphasis} className={word.emphasis?'border rounded p-1 text-xs bg-brass-soft':'border rounded p-1 text-xs'}
                            onClick={()=>updatePlanWithHistory({...plan,subtitles:plan.subtitles?.map(s=>s.id===seg.id?{...s,origin:'manual',words:s.words?.map((w,i)=>i===index?{...w,emphasis:!w.emphasis,color:undefined}:w)}:s)})}>{word.word}</button>)}
                        </div>}
                        <div className="flex gap-2 text-[10px]">
                          <label>Start<NumericInput aria-label="Caption start" step="0.01" min="0" max={seg.end_time-.01} value={seg.start_time}
                            className="w-full rounded border p-1" onCommit={nextValue=>{
                              const value=Math.max(0,Math.min(seg.end_time-.01,nextValue));
                              if(value===seg.start_time)return;
                              updatePlanWithHistory(editCaptionTiming(plan,seg.id,'start_time',value));
                            }} /></label>
                          <label>End<NumericInput aria-label="Caption end" step="0.01" min={seg.start_time+.01} max={plan.duration_seconds} value={seg.end_time}
                            className="w-full rounded border p-1" onCommit={nextValue=>{
                              const value=Math.min(plan.duration_seconds,Math.max(seg.start_time+.01,nextValue));
                              if(value===seg.end_time)return;
                              updatePlanWithHistory(editCaptionTiming(plan,seg.id,'end_time',value));
                            }} /></label>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'inserts' && <CreativePanel plan={plan} currentTime={currentTime} onChange={updatePlanWithHistory} onSeek={handleSeek} />}

          </div>
        </aside>

        {/* CENTER VIEWPORT: Video Preview & Playback Controls */}
        <main className="flex-1 min-h-0 min-w-0 flex flex-col bg-studio-hover items-center gap-2 p-2 sm:p-4 overflow-hidden">
          {/* Top Info Bar */}
          <div className="w-full max-w-sm shrink-0 flex items-center justify-between text-xs text-studio-muted font-mono pb-2">
            <span>RAYFLOW PREVIEW</span>
            <span className="font-semibold text-studio-text uppercase">
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
              className="relative rounded-xl overflow-hidden border border-studio-border bg-studio-canvas shrink-0"
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
              {!viewRenderedVideo && captionRegions.filter(region => region.bounds && currentTime >= region.start_time && currentTime < region.end_time && plan.subtitles?.some(caption => caption.id === region.caption_id)).map(region => {
                const [left, top, width, height] = region.bounds!;
                return <button key={`${region.caption_id}-${region.start_time}`} type="button"
                  aria-label={`Select preview caption: ${plan.subtitles?.find(caption => caption.id === region.caption_id)?.text}`}
                  aria-pressed={selectedCaptionIds.includes(region.caption_id)}
                  onClick={event => { setIsPlaying(false); selectCaption(region.caption_id, event.shiftKey || event.ctrlKey || event.metaKey); }}
                  style={{ left: `${left * 100}%`, top: `${top * 100}%`, width: `${width * 100}%`, height: `${height * 100}%` }}
                  className={`absolute rounded focus-visible:outline-accent ${selectedCaptionIds.includes(region.caption_id) ? 'ring-2 ring-accent' : 'hover:ring-1 hover:ring-accent'}`} />;
              })}
              <div className="absolute top-3 left-3 px-2 py-0.5 rounded bg-studio-canvas/80 backdrop-blur-sm text-[10px] font-mono text-white/80 border border-white/10 pointer-events-none">
                RAYFLOW {plan.aspect_ratio}
              </div>

              {renderStatus?.status === 'completed' && renderJobId && (
                <button
                  onClick={() => { setIsPlaying(false); setViewRenderedVideo(!viewRenderedVideo); }}
                  className="absolute bottom-3 right-3 px-2.5 py-1 rounded bg-studio-panel text-studio-text text-[11px] font-medium shadow-md hover:bg-studio-hover transition-colors border border-studio-border"
                >
                  {viewRenderedVideo ? 'Canvas Mode' : 'Watch Exported MP4'}
                </button>
              )}
            </div>
          </div>

          {/* Playback Controller */}
          <div data-testid="playback-controls"
          className="w-full max-w-md shrink-0 p-2 rounded-xl bg-studio-panel border border-studio-border shadow-sm flex items-center justify-between gap-4">
            <button
              onClick={handleTogglePlay}
              className="w-9 h-9 rounded-full bg-accent hover:bg-accent-hover text-white flex items-center justify-center transition-transform active:scale-95 shrink-0 shadow-sm"
              aria-label={isPlaying ? 'Pause' : 'Play'}
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="w-4 h-4 fill-white" /> : <Play className="w-4 h-4 fill-white ml-0.5" />}
            </button>

            {/* Time progress bar */}
            <div className="flex-1 flex flex-col gap-1">
              <div className="flex justify-between text-[11px] font-mono text-studio-muted">
                <span>{currentTime.toFixed(1)}s</span>
                <span>{plan.duration_seconds.toFixed(1)}s</span>
              </div>
              <input
                type="range"
                aria-label="Playback position"
                min="0"
                max={plan.duration_seconds}
                step={1 / PREVIEW_FPS}
                value={currentTime}
                onChange={e => handleSeek(parseFloat(e.target.value))}
                className="w-full accent-accent h-1.5 bg-studio-line rounded-lg cursor-pointer"
              />
            </div>

            <button
              onClick={() => {
                handleSeek(0.0);
                setIsPlaying(false);
              }}
              className="p-1.5 text-studio-quiet hover:text-studio-text transition-colors"
              title="Reset to 0s"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </main>

        {/* RIGHT PANEL: Voice & Text Editing Directives */}
        <aside className={`${mobilePanel === 'director' ? 'flex absolute inset-y-0 right-0 z-30 shadow-xl' : 'hidden'} xl:static xl:flex w-80 max-w-[85vw] border-l border-studio-border bg-studio-panel flex-col shrink-0 overflow-hidden`}>
          <button className="xl:hidden text-xs p-2 border-b" onClick={() => setMobilePanel(null)}>Close director</button>
          {/* Header */}
          <div className="p-4 border-b border-studio-border flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-accent" />
                <h3 className="text-sm font-semibold text-studio-text">
                  Rayflow AI Director
                </h3>
              </div>
              <p className="text-[11px] text-studio-muted mt-0.5">
                Direct your edit.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-2 h-2 rounded-full ${
                    directorConnection.configured ? 'bg-jade ring-2 ring-jade-border' : 'bg-studio-border'
                  }`}
                />
                <span className="text-[10px] font-mono text-studio-muted truncate max-w-[125px]">
                  <a href="#/connections">{directorConnection.label}</a>
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-studio-hover text-studio-text border border-studio-border">
                AI
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
                      ? 'bg-accent text-white'
                      : 'bg-studio-hover text-studio-text border border-studio-border'
                  }`}
                >
                  <p>{msg.text}</p>
                </div>
                <span className="text-[10px] text-studio-quiet mt-1 px-1">
                  {msg.time}
                </span>
              </div>
            ))}
          </div>

          {/* Suggested Directives */}
          {directionTips && <div className="px-4 py-2 border-t border-studio-line bg-studio-raised/60" role="region" aria-label="Try AI Direction">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-mono text-studio-quiet uppercase">Try AI Direction</span>
              <button type="button" aria-label="Close Try AI Direction panel" className="p-1 rounded hover:bg-studio-hover focus-visible:outline-accent"
                onClick={() => { setDirectionTips(false); try { sessionStorage.setItem('rayflow:direction-tips-dismissed', 'true'); } catch { /* Session storage is optional. */ } }}><X className="w-4 h-4" /></button>
            </div>
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
                  disabled={isInterpreting || !!pendingAIPlan}
                  onClick={() => handleExecuteCommand(cmd)}
                  className="text-[11px] px-2.5 py-1 rounded-full bg-studio-panel hover:bg-studio-hover border border-studio-border text-studio-text transition-colors text-left shadow-2xs"
                >
                  "{cmd}"
                </button>
              ))}
            </div>
          </div>}

          {/* Voice & Text Input */}
          <div className="p-3 border-t border-studio-border bg-studio-panel">
            {directorStage && <p role="status" className="text-xs text-studio-muted mb-2">{directorStage}</p>}
            <form
              onSubmit={e => {
                e.preventDefault();
                handleExecuteCommand();
              }}
              className="flex items-center gap-2"
            >
              <VoiceInputButton disabled={isInterpreting || !!pendingAIPlan || readOnly}
                onTranscript={setCommandInput} onSubmit={text => void handleExecuteCommand(text)}
                onError={setErrorMessage} onListeningChange={setIsListening} />

              <textarea
                aria-label="Edit direction"
                rows={2}
                maxLength={2000}
                value={commandInput}
                onChange={e => setCommandInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void handleExecuteCommand(); } }}
                placeholder={isListening ? 'Listening to your direction…' : 'Tell Rayflow what to edit…'}
                className="min-w-0 flex-1 resize-y bg-studio-panel border border-studio-border rounded-lg px-3 py-2 text-xs text-studio-text placeholder-studio-quiet focus:outline-none focus:border-accent shadow-2xs"
              />

              <Button
                type="submit"
                aria-label="Send edit direction"
                variant="primary"
                size="sm"
                disabled={!commandInput.trim() || isInterpreting || !!pendingAIPlan || readOnly}
              >
                {isInterpreting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              </Button>
            </form>

            {errorMessage && (
              <div className="mt-2 p-2 rounded-lg bg-danger-soft border border-danger-border text-danger text-[11px] flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errorMessage} <a className="underline" href="#/connections">Open AI settings</a></span>
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
        onSelectClip={selectClip}
        selectedCaptionIds={selectedCaptionIds}
        onSelectCaption={selectCaption}
        audioSelected={audioSelected}
        onSelectAudio={() => { selectClip(null); setAudioSelected(true); }}
        onSeek={handleSeek}
        onScrubCommit={(before, after) => {
          if (Math.abs(after - before) < .001) return;
          editOriginRef.current = { ...planRef.current, playhead_time: before };
          updatePlanWithHistory({ ...planRef.current, playhead_time: after });
        }}
        onUpdatePlan={updatePlanWithHistory}
        onOpenEffectsForBoundary={handleOpenEffectsForBoundary}
      />

      {pendingAIPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-studio-canvas/40 backdrop-blur-sm p-4">
          <div role="dialog" aria-modal="true" aria-label="Review your Rayflow edit" className="max-w-lg w-full max-h-[85vh] overflow-y-auto bg-studio-panel border border-studio-border rounded-2xl p-6 shadow-xl space-y-4">
            <div>
              <h3 className="text-base font-semibold text-studio-text">Review your Rayflow edit</h3>
              <p className="text-xs text-studio-muted mt-1">{pendingAIPlan.explanation}</p>
            </div>
            <div className="rounded-lg border border-studio-border bg-studio-hover p-3 space-y-2">
              <p className="text-[10px] uppercase font-mono text-studio-muted">Proposed actions</p>
              {pendingAIPlan.actions.length ? pendingAIPlan.actions.map((action, index) => (
                <div key={`${action.type}-${index}`} className="text-xs text-studio-text">
                  <span className="font-semibold">{index + 1}. {action.type.replaceAll('_', ' ')}</span>
                  <span className="block text-studio-muted break-words">{pendingAIPlan.applied_changes[index]}</span>
                </div>
              )) : <p className="text-xs text-studio-muted">No changes proposed.</p>}
            </div>
            <p className="text-[11px] text-studio-muted">Review the proposed changes, then apply them to your timeline.</p>
            <div className="flex justify-end gap-2">
              <button disabled={isInterpreting} className="text-xs px-3 py-2 rounded-lg border border-studio-border hover:bg-studio-hover" onClick={() => { setPendingAIPlan(null); pendingOrigin.current = null; setConversation(prev => [...prev, { sender: 'assistant', text: 'Proposal cancelled. No changes were applied.', time: 'Now' }]); }}>Cancel</button>
              <button className="text-xs px-3 py-2 rounded-lg bg-accent text-white disabled:opacity-50" disabled={isInterpreting} onClick={approveAIPlan}>
                {isInterpreting ? 'Applying…' : 'Approve and apply'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Render Modal */}
      {isRenderingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-studio-canvas/40 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="max-w-md w-full bg-studio-panel border border-studio-border rounded-2xl p-6 shadow-xl text-center space-y-4">
            <div className="w-12 h-12 rounded-xl bg-studio-hover border border-studio-border mx-auto flex items-center justify-center text-studio-text">
              {renderStatus?.status === 'completed' ? (
                <CheckCircle2 className="w-6 h-6 text-studio-text" />
              ) : renderStatus?.status === 'failed' ? (
                <AlertCircle className="w-6 h-6 text-danger" />
              ) : (
                <Film className="w-6 h-6 animate-pulse text-studio-text" />
              )}
            </div>

            <div>
              <h3 className="text-base font-semibold text-studio-text">
                {renderStatus?.status === 'completed'
                  ? 'Your Rayflow reel is ready'
                  : renderStatus?.status === 'failed'
                  ? 'Your reel could not be exported'
                  : 'Rendering your Rayflow reel'}
              </h3>
              <p className="text-xs text-studio-muted mt-1 leading-relaxed">
                {renderStatus?.status === 'completed'
                  ? `Your ${plan.aspect_ratio} reel is ready to download as an MP4, rendered with FFmpeg.`
                  : renderStatus?.status === 'failed'
                  ? renderStatus.error || 'FFmpeg could not finish this render. Your edit is still available in the studio.'
                  : `Rayflow is rendering your ${plan.aspect_ratio} frames, transitions, and soundtrack with FFmpeg...`}
              </p>
            </div>

            {/* Progress Bar */}
            {renderStatus && renderStatus.status !== 'failed' && (
              <div className="space-y-1.5">
                <div className="w-full h-2 bg-studio-hover rounded-full overflow-hidden border border-studio-border">
                  <div
                    className="h-full bg-accent transition-all duration-300"
                    style={{ width: `${renderStatus.progress}%` }}
                  />
                </div>
                <div className="flex justify-between text-[11px] font-mono text-studio-muted">
                  <span className="capitalize">{renderStatus.status}</span>
                  <span>{renderStatus.progress.toFixed(0)}%</span>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="pt-2 flex items-center justify-center gap-2.5">
              {renderJobId && (renderStatus?.status==='processing'||renderStatus?.status==='queued') && <button
                className="text-xs border rounded px-3 py-2" onClick={async()=>{
                  try{await creativeRequest(`/render/${renderJobId}/cancel`,{});setRenderStatus(previous=>previous?{...previous,status:'cancelled'}:previous);}
                  catch(error){setErrorMessage(error instanceof Error?error.message:'Could not cancel render.');}
                }}>Cancel render</button>}
              {renderStatus?.status === 'completed' && renderJobId && (
                <>
                  <a
                    href={getDownloadUrl(renderJobId)}
                    download={`rayflow_${renderJobId}.mp4`}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download MP4</span>
                  </a>
                  <button
                    onClick={() => {
                      setViewRenderedVideo(true);
                      setIsRenderingModalOpen(false);
                    }}
                    className="text-xs font-medium px-3.5 py-2 rounded-lg bg-studio-hover hover:bg-studio-line text-studio-text border border-studio-border transition-colors"
                  >
                    Watch in Preview
                  </button>
                </>
              )}

              <button
                onClick={() => setIsRenderingModalOpen(false)}
                className="text-xs font-medium px-3.5 py-2 rounded-lg text-studio-muted hover:text-studio-text hover:bg-studio-hover transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Auto-Edit Talking-Head Reel Workflow Modal (Stage 7) */}
      {isAutoEditModalOpen && (
        <div className="fixed inset-0 z-50 bg-studio-canvas/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-studio-panel border border-studio-border rounded-2xl max-w-md w-full max-h-[90vh] overflow-y-auto p-6 shadow-xl space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-studio-line pb-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-brass/10 flex items-center justify-center text-brass">
                  <Wand2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-studio-text">Auto Reel</h3>
                  <p className="text-[11px] text-studio-muted">Let Rayflow draft the captions, cuts, and B-roll.</p>
                </div>
              </div>
              <button
                onClick={() => setIsAutoEditModalOpen(false)}
                aria-label="Close Auto Reel"
                className="text-studio-quiet hover:text-studio-muted text-xs p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <label className="flex items-center gap-2 text-xs text-studio-text">
              <input type="checkbox" checked={includeCaptions} onChange={e => setIncludeCaptions(e.target.checked)} />
              Generate captions from speech
            </label>
            <p className="text-xs text-studio-muted">Output: {plan.aspect_ratio}. Uses your uploaded photos or primary video.</p>
            <label className="flex gap-2 text-xs"><input type="checkbox" checked={plan.auto_broll !== false} onChange={e => updatePlanWithHistory({...plan,auto_broll:e.target.checked})} />Find contextual B-roll on Pixabay</label>
            <label className="flex gap-2 text-xs"><input type="checkbox" checked={tightenSpeech} onChange={e=>setTightenSpeech(e.target.checked)}/>Trim greetings and long quiet pauses in new drafts</label>
            <label className="flex gap-2 text-xs"><input type="checkbox" checked={plan.list_sounds !== false} onChange={e => updatePlanWithHistory({...plan,list_sounds:e.target.checked})} />Add clicks to spoken list items</label>
            <SpeechModelSelect state={speechModels} value={whisperModel} onChange={setWhisperModel} label="Whisper model" />

            {/* Taste-personalized reel (Qloo-powered) */}
            <button
              type="button"
              onClick={() => setUseTasteReel(v => !v)}
              className={`w-full p-3 rounded-xl border text-left transition-all ${
                useTasteReel
                  ? 'border-accent bg-studio-raised ring-1 ring-accent shadow-xs'
                  : 'border-studio-border bg-studio-panel hover:border-studio-border'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold text-studio-text flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brass" /> Create a Reel Based on My Taste
                </span>
                <span className="text-[10px] font-mono text-studio-muted bg-studio-hover px-1.5 py-0.5 rounded">
                  Qloo
                </span>
              </div>
              <p className="text-[11px] text-studio-muted leading-relaxed">
                {hasTasteProfile
                  ? 'Use your saved taste profile to drive pacing, color, motion, and transitions. Produces a fully editable timeline.'
                  : 'Set up your taste profile first in “Discover Your Taste”, then return here.'}
              </p>
            </button>
            {useTasteReel && !hasTasteProfile && (
              <p className="text-[11px] text-brass">
                No taste profile found. <a href="#/taste" className="underline">Discover Your Taste</a> to enable this.
              </p>
            )}

            {/* Choose Reel Style */}
            <div className={`space-y-2 ${useTasteReel ? 'opacity-50 pointer-events-none' : ''}`}>
              <label className="text-xs font-semibold text-studio-text block">
                {useTasteReel ? 'Base style (chosen from your taste)' : 'Choose your reel style'}
              </label>
              <div className="space-y-2">
                {[
                  {
                    id: 'fitness_energy',
                    name: 'Fitness High Energy',
                    desc: 'Fast cuts, vivid color, highlighted words, and picture-in-picture B-roll.',
                    tag: 'Reels & TikTok'
                  },
                  {
                    id: 'minimalist',
                    name: 'Minimalist Clean',
                    desc: 'Full-frame fit, restrained color, phrase captions, and split-screen B-roll.',
                    tag: 'Educational & Podcasts'
                  },
                  {
                    id: 'cinematic',
                    name: 'Cinematic Story',
                    desc: 'Natural color, concise titles, and cuts that follow the speaker.',
                    tag: 'Storytelling & Lifestyle'
                  }
                ].map(style => (
                  <button
                    key={style.id}
                    onClick={() => setAutoEditStyle(style.id as any)}
                    className={`w-full p-3 rounded-xl border text-left transition-all ${
                      autoEditStyle === style.id
                        ? 'border-accent bg-studio-raised ring-1 ring-accent shadow-xs'
                        : 'border-studio-border bg-studio-panel hover:border-studio-border'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-studio-text">{style.name}</span>
                      <span className="text-[10px] font-mono text-studio-muted bg-studio-hover px-1.5 py-0.5 rounded">
                        {style.tag}
                      </span>
                    </div>
                    <p className="text-[11px] text-studio-muted leading-relaxed">
                      {style.desc}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-studio-line">
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
                disabled={isAutoEditing || images.length === 0 || (useTasteReel && !hasTasteProfile) || (!whisperModel && (includeCaptions || plan.auto_broll || plan.list_sounds) && (!!audio || images.some(item => item.media_type === 'video')))}
                className="bg-accent hover:bg-accent-hover text-white flex items-center gap-1.5"
              >
                {isAutoEditing ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>{autoStage || 'Preparing your Rayflow draft'}…</span>
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
