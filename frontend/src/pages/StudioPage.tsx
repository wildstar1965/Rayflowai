import React, { useState, useEffect, useRef } from 'react';
import { SpecularButton } from '../components/ui/SpecularButton';
import {
  EditingPlan,
  UploadedImage,
  UploadedAudio,
  AudioAnalysisResult,
  RenderJobStatus,
  ClipConfig
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
  getMediaUrl
} from '../services/api';
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
  Maximize2
} from 'lucide-react';

interface StudioPageProps {
  onBackToHome: () => void;
}

export const StudioPage: React.FC<StudioPageProps> = ({ onBackToHome }) => {
  // Project State
  const [projectName, setProjectName] = useState('Untitled Cinematic Reel #1');
  const [activeTab, setActiveTab] = useState<'photos' | 'music' | 'style' | 'title'>('photos');
  const [aspectRatio, setAspectRatio] = useState<'9:16' | '16:9' | '1:1'>('9:16');

  // Media State
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [audio, setAudio] = useState<UploadedAudio | null>(null);
  const [audioAnalysis, setAudioAnalysis] = useState<AudioAnalysisResult | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isAnalyzingAudio, setIsAnalyzingAudio] = useState(false);

  // Editing Plan State
  const [plan, setPlan] = useState<EditingPlan>({
    duration_seconds: 15.0,
    aspect_ratio: '9:16',
    style: 'cinematic',
    beat_sync: true,
    cut_pacing: 'balanced',
    motion: 'slow_zoom',
    title: {
      enabled: true,
      text: 'RAYFLOW CINEMA',
      gradient: ['#67E8F9', '#3B82F6'],
      subtitle: 'A Satyajit Ray Tribute'
    },
    clips: []
  });

  // Undo / Redo History
  const [history, setHistory] = useState<EditingPlan[]>([]);
  const [redoStack, setRedoStack] = useState<EditingPlan[]>([]);

  // Assistant / Voice State
  const [commandInput, setCommandInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isInterpreting, setIsInterpreting] = useState(false);
  const [conversation, setConversation] = useState<Array<{ sender: 'user' | 'assistant'; text: string; time: string }>>([
    {
      sender: 'assistant',
      text: 'Welcome to RayFlow AI. Upload your photos and soundtrack, then speak or type creative instructions to direct your reel.',
      time: 'Just now'
    }
  ]);

  // Video Preview & Playback State
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0.0);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const previewCanvasRef = useRef<HTMLCanvasElement>(null);
  const videoPlayerRef = useRef<HTMLVideoElement>(null);

  // Rendering State
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [renderStatus, setRenderStatus] = useState<RenderJobStatus | null>(null);
  const [isRenderingModalOpen, setIsRenderingModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Push new plan to history
  const updatePlanWithHistory = (newPlan: EditingPlan) => {
    setHistory(prev => [...prev, plan]);
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
  const refreshTimeline = async (currentPlan: EditingPlan, currentImages: UploadedImage[], currentAudio: UploadedAudio | null) => {
    if (currentImages.length === 0) return;
    try {
      const updated = await generateProjectPlan(
        currentPlan,
        currentImages.map(img => img.filename),
        currentAudio ? currentAudio.filename : undefined
      );
      setPlan(updated);
    } catch (err: any) {
      console.error('Failed to generate project plan:', err);
    }
  };

  // Pre-load sample media for instant testing
  const handleLoadSampleMedia = async () => {
    const sampleImages: UploadedImage[] = [
      {
        filename: 'test_render_sample_0.jpg',
        original_name: 'Ray_Composition_1.jpg',
        size: 320000,
        url: '/api/uploads/test_render_sample_0.jpg'
      },
      {
        filename: 'test_render_sample_1.jpg',
        original_name: 'Charulata_Light_2.jpg',
        size: 290000,
        url: '/api/uploads/test_render_sample_1.jpg'
      },
      {
        filename: 'test_render_sample_2.jpg',
        original_name: 'Apu_Cinematography_3.jpg',
        size: 310000,
        url: '/api/uploads/test_render_sample_2.jpg'
      }
    ];
    setImages(sampleImages);

    const updatedPlan: EditingPlan = {
      ...plan,
      duration_seconds: 12.0,
      title: {
        enabled: true,
        text: 'PATHER PANCHALI',
        gradient: ['#67E8F9', '#3B82F6'],
        subtitle: 'Directed with RayFlow'
      }
    };
    updatePlanWithHistory(updatedPlan);
    await refreshTimeline(updatedPlan, sampleImages, audio);

    setConversation(prev => [
      ...prev,
      {
        sender: 'assistant',
        text: 'Loaded 3 Satyajit Ray tribute sample photographs with a 12-second balanced cinematic plan.',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ]);
  };

  // Photo Upload Handler
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadImages(Array.from(e.target.files));
      const combined = [...images, ...uploaded];
      setImages(combined);
      await refreshTimeline(plan, combined, audio);
      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `Uploaded ${uploaded.length} photographs. Timeline synchronized.`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to upload images');
    } finally {
      setIsUploading(false);
    }
  };

  // Audio Upload Handler
  const handleAudioUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadAudio(file);
      setAudio(uploaded);

      // Analyze beats automatically
      setIsAnalyzingAudio(true);
      const analysis = await analyzeAudioFile(uploaded.filename);
      setAudioAnalysis(analysis);
      setIsAnalyzingAudio(false);

      await refreshTimeline(plan, images, uploaded);

      setConversation(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `Soundtrack "${uploaded.original_name}" uploaded. Beat tracking complete: detected tempo of ${analysis.tempo} BPM with ${analysis.beat_count} beats.`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Audio upload or beat analysis failed');
    } finally {
      setIsUploading(false);
      setIsAnalyzingAudio(false);
    }
  };

  // Remove photo
  const handleRemoveImage = (index: number) => {
    const updated = images.filter((_, i) => i !== index);
    setImages(updated);
    refreshTimeline(plan, updated, audio);
  };

  // Reorder photo
  const handleMoveImage = (index: number, direction: 'up' | 'down') => {
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= images.length) return;
    const copy = [...images];
    const [moved] = copy.splice(index, 1);
    copy.splice(target, 0, moved);
    setImages(copy);
    refreshTimeline(plan, copy, audio);
  };

  // Voice Recognition via Web Speech API
  const handleVoiceToggle = () => {
    if (isListening) {
      setIsListening(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setErrorMessage('Speech recognition is not supported in this browser. Please type your command in the text box below.');
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

      recognition.onerror = (event: any) => {
        setIsListening(false);
        if (event.error === 'not-allowed') {
          setErrorMessage('Microphone access was denied. Please allow microphone permissions or use text input.');
        } else {
          setErrorMessage(`Speech recognition error: ${event.error}`);
        }
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } catch (err: any) {
      setIsListening(false);
      setErrorMessage('Could not initialize microphone. Please use text input.');
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

      // Re-calculate clips
      if (images.length > 0) {
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
      setErrorMessage(err.message || 'Failed to interpret command');
    } finally {
      setIsInterpreting(false);
    }
  };

  // Start Video Render
  const handleStartRender = async () => {
    if (images.length === 0) {
      setErrorMessage('Please upload at least one photograph to render a video.');
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
                  text: 'Reel rendered successfully! Your 1080×1920 MP4 is ready for preview and download.',
                  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
              ]);
            }
          }
        } catch {
          clearInterval(interval);
        }
      }, 1500);
    } catch (err: any) {
      setErrorMessage(err.message || 'Render failed to start.');
      setIsRenderingModalOpen(false);
    }
  };

  // Playback timer loop for canvas preview
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
            return 0.0;
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

  // Find active clip for current playback time
  const currentClip = plan.clips.find(
    c => currentTime >= c.start_time && currentTime < c.start_time + c.duration
  ) || plan.clips[0];

  // Draw simulated cinematic preview on canvas
  useEffect(() => {
    const canvas = previewCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    ctx.fillStyle = '#08090D';
    ctx.fillRect(0, 0, w, h);

    if (currentClip && currentClip.image_url) {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = getMediaUrl(currentClip.image_url);

      img.onload = () => {
        // Calculate crop to fill
        const scale = Math.max(w / img.width, h / img.height);
        // Add subtle Ken Burns zoom animation
        const clipProgress = (currentTime - currentClip.start_time) / currentClip.duration;
        const zoom = currentClip.motion === 'zoom_out'
          ? 1.15 - 0.1 * Math.min(1, Math.max(0, clipProgress))
          : 1.05 + 0.1 * Math.min(1, Math.max(0, clipProgress));

        const finalScale = scale * zoom;
        const sw = img.width * finalScale;
        const sh = img.height * finalScale;
        const sx = (w - sw) / 2;
        const sy = (h - sh) / 2;

        ctx.drawImage(img, sx, sy, sw, sh);

        // Apply style filter
        if (plan.style === 'noir') {
          ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
          ctx.fillRect(0, 0, w, h);
          // Grayscale blend
          ctx.globalCompositeOperation = 'color';
          ctx.fillStyle = '#808080';
          ctx.fillRect(0, 0, w, h);
          ctx.globalCompositeOperation = 'source-over';
        } else if (plan.style === 'vintage') {
          ctx.globalCompositeOperation = 'color';
          ctx.fillStyle = '#D97706';
          ctx.fillRect(0, 0, w, h);
          ctx.globalCompositeOperation = 'source-over';
        }

        // Draw title overlay if enabled (during first 4 seconds)
        if (plan.title.enabled && plan.title.text && currentTime <= 4.0) {
          ctx.save();
          const titleAlpha = currentTime < 0.5
            ? currentTime / 0.5
            : currentTime > 3.2
            ? (4.0 - currentTime) / 0.8
            : 1.0;
          ctx.globalAlpha = Math.max(0, Math.min(1, titleAlpha));

          ctx.textAlign = 'center';
          ctx.font = 'bold 36px Inter, sans-serif';

          // Gradient
          const gradient = ctx.createLinearGradient(0, h * 0.4, 0, h * 0.45);
          gradient.addColorStop(0, plan.title.gradient[0] || '#67E8F9');
          gradient.addColorStop(1, plan.title.gradient[1] || '#3B82F6');

          ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
          ctx.shadowBlur = 12;
          ctx.fillStyle = gradient;
          ctx.fillText(plan.title.text, w / 2, h * 0.45);

          if (plan.title.subtitle) {
            ctx.font = '500 16px Inter, sans-serif';
            ctx.fillStyle = 'rgba(245, 247, 251, 0.85)';
            ctx.fillText(plan.title.subtitle, w / 2, h * 0.45 + 32);
          }
          ctx.restore();
        }
      };
    } else {
      // Empty state on canvas
      ctx.fillStyle = '#181B24';
      ctx.fillRect(0, 0, w, h);
      ctx.textAlign = 'center';
      ctx.font = '500 16px Inter, sans-serif';
      ctx.fillStyle = '#9299AA';
      ctx.fillText('Upload photographs to preview edit', w / 2, h / 2);
    }
  }, [currentTime, currentClip, plan]);

  return (
    <div className="flex flex-col h-screen bg-[#08090D] text-[#F5F7FB] overflow-hidden select-none">
      {/* Top Navigation Bar */}
      <header className="h-14 border-b border-border-subtle bg-surface/90 backdrop-blur-md px-5 flex items-center justify-between z-30 shrink-0">
        {/* Left: Brand & Tribute */}
        <div className="flex items-center gap-4">
          <button
            onClick={onBackToHome}
            className="flex items-center gap-2 hover:opacity-80 transition-opacity"
            title="Return to Landing Page"
          >
            <div className="w-2.5 h-2.5 rounded-full bg-accent-blue shadow-[0_0_10px_#3B82F6]" />
            <span className="font-bold tracking-wider font-mono text-sm">RAYFLOW</span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-accent-blue/15 text-accent-cyan border border-accent-blue/30 font-mono">
              STUDIO
            </span>
          </button>

          <div className="h-4 w-px bg-border-medium hidden sm:block" />

          {/* Project Name */}
          <input
            type="text"
            value={projectName}
            onChange={e => setProjectName(e.target.value)}
            className="bg-transparent border border-transparent hover:border-border-subtle focus:border-accent-blue/50 rounded px-2 py-0.5 text-xs text-text-primary font-medium outline-none transition-all w-48 sm:w-60 truncate"
          />

          <span className="text-[10px] font-mono text-text-muted hidden md:inline border border-white/5 px-2 py-0.5 rounded">
            Tribute to Satyajit Ray
          </span>
        </div>

        {/* Center: Aspect Ratio & Undo/Redo */}
        <div className="hidden lg:flex items-center gap-3">
          <div className="flex items-center bg-surface-elevated rounded-lg p-1 border border-border-subtle text-xs">
            {(['9:16', '16:9', '1:1'] as const).map(ratio => (
              <button
                key={ratio}
                onClick={() => {
                  setAspectRatio(ratio);
                  const updated = { ...plan, aspect_ratio: ratio };
                  updatePlanWithHistory(updated);
                  refreshTimeline(updated, images, audio);
                }}
                className={`px-2.5 py-1 rounded font-mono transition-colors ${
                  plan.aspect_ratio === ratio
                    ? 'bg-accent-blue text-white font-semibold'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {ratio}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={handleUndo}
              disabled={history.length === 0}
              className="p-1.5 rounded hover:bg-surface-elevated text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Undo2 className="w-4 h-4" />
            </button>
            <button
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              className="p-1.5 rounded hover:bg-surface-elevated text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:pointer-events-none transition-colors"
              title="Redo (Ctrl+Y)"
            >
              <Redo2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Right: Export Button */}
        <div className="flex items-center gap-3">
          {images.length === 0 && (
            <button
              onClick={handleLoadSampleMedia}
              className="text-xs px-3 py-1.5 rounded-lg bg-surface-elevated hover:bg-surface-hover border border-accent-cyan/30 text-accent-cyan transition-colors hidden sm:flex items-center gap-1.5 font-medium"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Load Sample Project</span>
            </button>
          )}

          <SpecularButton
            size="sm"
            radius={14}
            tint="#3B82F6"
            tintOpacity={0.2}
            lineColor="#67E8F9"
            textColor="#FFFFFF"
            onClick={handleStartRender}
            className="font-semibold px-4 py-2 text-xs shadow-md shadow-accent-blue/20"
          >
            <div className="flex items-center gap-1.5">
              <Film className="w-3.5 h-3.5 text-accent-cyan" />
              <span>Export Reel</span>
            </div>
          </SpecularButton>
        </div>
      </header>

      {/* Main Workspace: 3 Columns (Left Media, Center Preview, Right Assistant) */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT SIDEBAR: Media & Assets */}
        <aside className="w-72 sm:w-80 border-r border-border-subtle bg-surface/50 flex flex-col shrink-0">
          {/* Sidebar Tabs */}
          <div className="flex items-center border-b border-border-subtle bg-surface px-2 pt-2 gap-1 text-xs">
            <button
              onClick={() => setActiveTab('photos')}
              className={`flex items-center gap-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
                activeTab === 'photos'
                  ? 'border-accent-blue text-accent-blue'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Photos ({images.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('music')}
              className={`flex items-center gap-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
                activeTab === 'music'
                  ? 'border-accent-blue text-accent-blue'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Music className="w-3.5 h-3.5" />
              <span>Music</span>
            </button>

            <button
              onClick={() => setActiveTab('style')}
              className={`flex items-center gap-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
                activeTab === 'style'
                  ? 'border-accent-blue text-accent-blue'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Style</span>
            </button>

            <button
              onClick={() => setActiveTab('title')}
              className={`flex items-center gap-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
                activeTab === 'title'
                  ? 'border-accent-blue text-accent-blue'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Type className="w-3.5 h-3.5" />
              <span>Title</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* PHOTOS TAB */}
            {activeTab === 'photos' && (
              <div className="space-y-3">
                <label className="border-2 border-dashed border-border-medium hover:border-accent-blue/50 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-colors group bg-surface-elevated/40">
                  <Upload className="w-5 h-5 text-accent-blue mb-1 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-medium text-text-primary">Add Photographs</span>
                  <span className="text-[10px] text-text-muted mt-0.5">JPG, PNG, WebP</span>
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    onChange={handleImageUpload}
                    className="hidden"
                  />
                </label>

                {isUploading && (
                  <div className="flex items-center justify-center gap-2 py-2 text-xs text-accent-cyan">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Uploading photographs...</span>
                  </div>
                )}

                {images.length === 0 ? (
                  <div className="text-center py-8 px-4 text-xs text-text-muted space-y-2">
                    <p>No photos uploaded yet.</p>
                    <button
                      onClick={handleLoadSampleMedia}
                      className="text-accent-cyan hover:underline font-medium"
                    >
                      Click to load Ray tribute sample photos
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {images.map((img, idx) => (
                      <div
                        key={img.filename + idx}
                        className="flex items-center justify-between p-2 rounded-lg bg-surface-elevated border border-border-subtle hover:border-border-medium transition-all group"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <img
                            src={getMediaUrl(img.url)}
                            alt=""
                            className="w-10 h-10 object-cover rounded bg-black shrink-0"
                          />
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-text-primary truncate">
                              {img.original_name}
                            </p>
                            <p className="text-[10px] text-text-muted font-mono">
                              {(img.size / 1024).toFixed(0)} KB
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100">
                          <button
                            onClick={() => handleMoveImage(idx, 'up')}
                            disabled={idx === 0}
                            className="p-1 hover:text-accent-blue disabled:opacity-20"
                            title="Move Up"
                          >
                            <ArrowUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleMoveImage(idx, 'down')}
                            disabled={idx === images.length - 1}
                            className="p-1 hover:text-accent-blue disabled:opacity-20"
                            title="Move Down"
                          >
                            <ArrowDown className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleRemoveImage(idx)}
                            className="p-1 hover:text-red-400"
                            title="Delete"
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
                <label className="border-2 border-dashed border-border-medium hover:border-accent-violet/50 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-colors group bg-surface-elevated/40">
                  <Music className="w-5 h-5 text-accent-violet mb-1 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-medium text-text-primary">
                    {audio ? 'Replace Music Track' : 'Upload Soundtrack'}
                  </span>
                  <span className="text-[10px] text-text-muted mt-0.5">MP3, WAV, M4A</span>
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleAudioUpload}
                    className="hidden"
                  />
                </label>

                {isAnalyzingAudio && (
                  <div className="flex items-center justify-center gap-2 py-2 text-xs text-accent-violet">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Analyzing beats with Librosa...</span>
                  </div>
                )}

                {audio ? (
                  <div className="p-3 rounded-xl bg-surface-elevated border border-border-medium space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="min-w-0">
                        <span className="text-xs font-semibold text-text-primary block truncate">
                          {audio.original_name}
                        </span>
                        <span className="text-[10px] text-text-muted font-mono">
                          {(audio.size / (1024 * 1024)).toFixed(1)} MB
                        </span>
                      </div>
                      <span className="text-xs px-2 py-0.5 rounded bg-accent-violet/20 text-accent-violet border border-accent-violet/30 font-mono">
                        Active
                      </span>
                    </div>

                    {audioAnalysis && (
                      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono pt-2 border-t border-border-subtle">
                        <div className="bg-surface/60 p-2 rounded">
                          <span className="text-text-muted block text-[10px]">TEMPO</span>
                          <span className="text-accent-cyan font-bold">{audioAnalysis.tempo} BPM</span>
                        </div>
                        <div className="bg-surface/60 p-2 rounded">
                          <span className="text-text-muted block text-[10px]">BEATS</span>
                          <span className="text-accent-blue font-bold">{audioAnalysis.beat_count} DETECTED</span>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-6 text-xs text-text-muted">
                    No soundtrack uploaded. If left empty, RayFlow will render a clean audio track.
                  </div>
                )}
              </div>
            )}

            {/* STYLE TAB */}
            {activeTab === 'style' && (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-text-secondary block mb-2">
                    Cinematic Style Preset
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'cinematic', label: 'Director Ray' },
                      { id: 'noir', label: 'Film Noir' },
                      { id: 'vintage', label: 'Vintage Kodachrome' },
                      { id: 'vibrant', label: 'Vibrant Neo' },
                      { id: 'minimal', label: 'Minimal Studio' }
                    ].map(st => (
                      <button
                        key={st.id}
                        onClick={() => {
                          const updated = { ...plan, style: st.id as any };
                          updatePlanWithHistory(updated);
                        }}
                        className={`p-2 rounded-lg text-left text-xs font-medium border transition-colors ${
                          plan.style === st.id
                            ? 'bg-accent-blue/20 border-accent-blue text-accent-cyan'
                            : 'bg-surface-elevated border-border-subtle text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {st.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-text-secondary block mb-2">
                    Cut Pacing Strategy
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: 'slow', label: 'Slow & Poetic (~4s)' },
                      { id: 'balanced', label: 'Balanced (~2.5s)' },
                      { id: 'fast', label: 'Rapid Cut (~1.5s)' },
                      { id: 'beat_driven', label: 'Direct Beat Hit' }
                    ].map(p => (
                      <button
                        key={p.id}
                        onClick={() => {
                          const updated = { ...plan, cut_pacing: p.id as any };
                          updatePlanWithHistory(updated);
                          refreshTimeline(updated, images, audio);
                        }}
                        className={`p-2 rounded-lg text-left text-xs font-medium border transition-colors ${
                          plan.cut_pacing === p.id
                            ? 'bg-accent-violet/20 border-accent-violet text-accent-violet'
                            : 'bg-surface-elevated border-border-subtle text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-text-secondary block mb-2">
                    Reel Duration: {plan.duration_seconds}s
                  </label>
                  <input
                    type="range"
                    min="5"
                    max="60"
                    step="1"
                    value={plan.duration_seconds}
                    onChange={e => {
                      const updated = { ...plan, duration_seconds: parseFloat(e.target.value) };
                      setPlan(updated);
                      refreshTimeline(updated, images, audio);
                    }}
                    className="w-full accent-accent-blue cursor-pointer"
                  />
                </div>
              </div>
            )}

            {/* TITLE TAB */}
            {activeTab === 'title' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-text-secondary">Enable Title Typography</span>
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
                    className="accent-accent-blue w-4 h-4 rounded cursor-pointer"
                  />
                </div>

                {plan.title.enabled && (
                  <>
                    <div>
                      <label className="text-xs font-medium text-text-secondary block mb-1">
                        Main Title Text
                      </label>
                      <input
                        type="text"
                        value={plan.title.text}
                        onChange={e => {
                          const updated = {
                            ...plan,
                            title: { ...plan.title, text: e.target.value.toUpperCase() }
                          };
                          setPlan(updated);
                        }}
                        placeholder="ENTER TITLE"
                        className="w-full bg-surface-elevated border border-border-medium rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-wider text-text-primary outline-none focus:border-accent-blue"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-text-secondary block mb-1">
                        Subtitle (Optional)
                      </label>
                      <input
                        type="text"
                        value={plan.title.subtitle || ''}
                        onChange={e => {
                          const updated = {
                            ...plan,
                            title: { ...plan.title, subtitle: e.target.value }
                          };
                          setPlan(updated);
                        }}
                        placeholder="e.g. A Satyajit Ray Tribute"
                        className="w-full bg-surface-elevated border border-border-medium rounded-lg px-3 py-2 text-xs text-text-secondary outline-none focus:border-accent-blue"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-text-secondary block mb-2">
                        Gradient Preset
                      </label>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {[
                          { name: 'Electric Blue', colors: ['#67E8F9', '#3B82F6'] },
                          { name: 'Vivid Violet', colors: ['#C084FC', '#8B5CF6'] },
                          { name: 'Golden Film', colors: ['#FDE047', '#F59E0B'] },
                          { name: 'Monochrome', colors: ['#FFFFFF', '#94A3B8'] }
                        ].map(grad => (
                          <button
                            key={grad.name}
                            onClick={() => {
                              const updated = {
                                ...plan,
                                title: { ...plan.title, gradient: grad.colors }
                              };
                              updatePlanWithHistory(updated);
                            }}
                            className={`p-2 rounded-lg border flex items-center gap-2 ${
                              plan.title.gradient[0] === grad.colors[0]
                                ? 'border-accent-cyan bg-surface-elevated'
                                : 'border-border-subtle bg-surface hover:border-border-medium'
                            }`}
                          >
                            <span
                              className="w-4 h-4 rounded-full shrink-0"
                              style={{
                                background: `linear-gradient(135deg, ${grad.colors[0]}, ${grad.colors[1]})`
                              }}
                            />
                            <span className="truncate">{grad.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* CENTER COLUMN: Video Viewport & Playback Controls */}
        <main className="flex-1 flex flex-col bg-[#08090D] items-center justify-between p-4 overflow-hidden">
          {/* Top Info Bar */}
          <div className="w-full max-w-sm flex items-center justify-between text-xs text-text-muted font-mono pb-2">
            <span>PREVIEW COMPOSITION</span>
            <span className="text-accent-cyan uppercase">{plan.style} • {plan.cut_pacing}</span>
          </div>

          {/* Central 9:16 Viewport Box */}
          <div className="relative flex-1 flex items-center justify-center w-full max-h-[64vh]">
            <div
              className={`relative rounded-2xl overflow-hidden border border-border-medium shadow-2xl bg-black transition-all duration-300 ${
                plan.aspect_ratio === '9:16'
                  ? 'aspect-[9/16] h-full max-h-[580px]'
                  : plan.aspect_ratio === '16:9'
                  ? 'aspect-[16/9] w-full max-w-[640px]'
                  : 'aspect-square h-full max-h-[480px]'
              }`}
            >
              {/* If rendered MP4 available, show real HTML5 video */}
              {renderStatus?.status === 'completed' && renderStatus.download_url ? (
                <video
                  ref={videoPlayerRef}
                  src={getDownloadUrl(renderStatus.job_id)}
                  controls
                  playsInline
                  className="w-full h-full object-contain"
                />
              ) : (
                /* Interactive Canvas Preview */
                <canvas
                  ref={previewCanvasRef}
                  width={720}
                  height={1280}
                  className="w-full h-full object-cover"
                />
              )}

              {/* Watermark badge */}
              <div className="absolute top-3 left-3 px-2 py-0.5 rounded bg-black/60 backdrop-blur-md text-[10px] font-mono text-white/70 border border-white/10 pointer-events-none">
                RAYFLOW {plan.aspect_ratio}
              </div>
            </div>
          </div>

          {/* Viewport Playback Controller */}
          <div className="w-full max-w-md mt-3 p-2.5 rounded-xl bg-surface-elevated/80 border border-border-subtle flex items-center justify-between gap-4">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className="w-9 h-9 rounded-full bg-accent-blue hover:bg-accent-blue/90 flex items-center justify-center text-white transition-transform active:scale-95 shadow-md shadow-accent-blue/30 shrink-0"
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="w-4 h-4 fill-white" /> : <Play className="w-4 h-4 fill-white ml-0.5" />}
            </button>

            {/* Time progress bar */}
            <div className="flex-1 flex flex-col gap-1">
              <div className="flex justify-between text-[11px] font-mono text-text-secondary">
                <span>{currentTime.toFixed(1)}s</span>
                <span>{plan.duration_seconds.toFixed(1)}s</span>
              </div>
              <input
                type="range"
                min="0"
                max={plan.duration_seconds}
                step="0.1"
                value={currentTime}
                onChange={e => setCurrentTime(parseFloat(e.target.value))}
                className="w-full accent-accent-blue h-1.5 bg-surface rounded-lg cursor-pointer"
              />
            </div>

            <button
              onClick={() => {
                setCurrentTime(0.0);
                setIsPlaying(false);
              }}
              className="p-2 text-text-muted hover:text-text-primary transition-colors"
              title="Reset to 0s"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </main>

        {/* RIGHT SIDEBAR: Editing Assistant (Voice-First Director) */}
        <aside className="w-80 sm:w-96 border-l border-border-subtle bg-surface/50 flex flex-col shrink-0">
          {/* Header */}
          <div className="p-4 border-b border-border-subtle flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-accent-cyan" />
                <h3 className="text-sm font-bold text-text-primary font-cinematic">
                  Direct your edit
                </h3>
              </div>
              <p className="text-[11px] text-text-secondary mt-0.5">
                Voice-guided creative direction
              </p>
            </div>

            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent-blue/15 text-accent-cyan border border-accent-blue/30">
              AI DIRECTOR
            </span>
          </div>

          {/* Active Settings Summary Pills */}
          <div className="px-4 py-2 border-b border-border-subtle bg-surface/80 flex flex-wrap gap-1.5 text-[10px] font-mono">
            <span className="px-2 py-0.5 rounded bg-surface-elevated text-text-secondary border border-border-subtle">
              ⏱ {plan.duration_seconds}s
            </span>
            <span className="px-2 py-0.5 rounded bg-surface-elevated text-text-secondary border border-border-subtle uppercase">
              🎬 {plan.style}
            </span>
            <span className="px-2 py-0.5 rounded bg-surface-elevated text-text-secondary border border-border-subtle">
              ✂ {plan.cut_pacing}
            </span>
            <span className="px-2 py-0.5 rounded bg-surface-elevated text-accent-cyan border border-accent-cyan/30">
              🎵 {plan.beat_sync ? 'Beat-Synced' : 'Free Timing'}
            </span>
          </div>

          {/* Conversation History */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {conversation.map((msg, i) => (
              <div
                key={i}
                className={`flex flex-col ${
                  msg.sender === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed ${
                    msg.sender === 'user'
                      ? 'bg-accent-blue text-white rounded-tr-none'
                      : 'bg-surface-elevated border border-border-medium text-text-primary rounded-tl-none'
                  }`}
                >
                  {msg.text}
                </div>
                <span className="text-[9px] text-text-muted mt-1 px-1 font-mono">
                  {msg.time}
                </span>
              </div>
            ))}

            {isInterpreting && (
              <div className="flex items-center gap-2 text-xs text-accent-cyan">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Interpreting creative direction...</span>
              </div>
            )}
          </div>

          {/* Suggested Prompts */}
          <div className="px-4 py-2 border-t border-border-subtle bg-surface/40">
            <span className="text-[10px] font-mono text-text-muted block mb-1.5 uppercase">
              Suggested instructions:
            </span>
            <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto pb-1">
              {[
                'Make the cuts faster',
                'Sync cuts to strong beats',
                'Change style to vintage film',
                'Make a 20-second reel',
                'Use slow zooms with cyan title'
              ].map(cmd => (
                <button
                  key={cmd}
                  onClick={() => handleExecuteCommand(cmd)}
                  className="text-[11px] px-2.5 py-1 rounded-full bg-surface-elevated hover:bg-surface-hover border border-border-subtle text-text-secondary hover:text-text-primary transition-colors text-left"
                >
                  "{cmd}"
                </button>
              ))}
            </div>
          </div>

          {/* Voice & Text Input Box */}
          <div className="p-3 border-t border-border-subtle bg-surface">
            <div className="flex items-center gap-2">
              <button
                onClick={handleVoiceToggle}
                className={`p-3 rounded-full transition-all duration-300 relative ${
                  isListening
                    ? 'bg-red-500 text-white animate-pulse shadow-lg shadow-red-500/50'
                    : 'bg-accent-blue/15 hover:bg-accent-blue/25 text-accent-blue border border-accent-blue/30'
                }`}
                title={isListening ? 'Stop listening' : 'Start voice command'}
              >
                {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
              </button>

              <div className="flex-1 relative">
                <input
                  type="text"
                  value={commandInput}
                  onChange={e => setCommandInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleExecuteCommand()}
                  placeholder={isListening ? 'Listening to your voice...' : 'Tell RayFlow what to edit...'}
                  className="w-full bg-surface-elevated border border-border-medium rounded-full px-4 py-2.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-accent-blue pr-9"
                />
                <button
                  onClick={() => handleExecuteCommand()}
                  disabled={!commandInput.trim()}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-accent-cyan hover:text-white disabled:opacity-30 disabled:pointer-events-none transition-colors"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {isListening && (
              <p className="text-[11px] text-accent-cyan text-center mt-2 animate-pulse font-mono">
                🎙 Listening... Speak your editing instructions
              </p>
            )}

            {errorMessage && (
              <div className="mt-2 p-2 rounded bg-red-500/10 border border-red-500/30 text-red-400 text-[11px] flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{errorMessage}</span>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* BOTTOM TIMELINE */}
      <footer className="h-36 border-t border-border-subtle bg-surface flex flex-col shrink-0 z-20">
        {/* Timeline Header & Time Markers */}
        <div className="h-7 border-b border-border-subtle px-4 flex items-center justify-between text-[10px] font-mono text-text-muted bg-surface-elevated/50">
          <div className="flex items-center gap-2">
            <span>TIMELINE TRACKS</span>
            <span className="text-text-secondary">• {plan.clips.length} CLIPS</span>
          </div>
          <div className="flex items-center gap-6">
            <span>00:00</span>
            <span>00:04</span>
            <span>00:08</span>
            <span>00:12</span>
            <span>00:{plan.duration_seconds.toFixed(0).padStart(2, '0')}</span>
          </div>
        </div>

        {/* Tracks Area */}
        <div className="flex-1 p-2 space-y-1.5 overflow-x-auto relative">
          {/* Images Track */}
          <div className="h-12 bg-surface-elevated rounded-lg p-1 flex items-center gap-1 border border-border-subtle relative overflow-hidden">
            <span className="text-[9px] font-mono text-text-muted px-1 shrink-0 uppercase">IMG</span>
            {plan.clips.length === 0 ? (
              <div className="text-xs text-text-muted italic px-2">
                No clips generated. Add photographs to populate timeline.
              </div>
            ) : (
              plan.clips.map((clip, i) => {
                const widthPercent = (clip.duration / plan.duration_seconds) * 100;
                const isSelected = selectedClipId === clip.id;
                return (
                  <div
                    key={clip.id + i}
                    onClick={() => {
                      setSelectedClipId(clip.id);
                      setCurrentTime(clip.start_time);
                    }}
                    style={{ width: `${widthPercent}%` }}
                    className={`h-full rounded relative overflow-hidden cursor-pointer border transition-all ${
                      isSelected
                        ? 'border-accent-cyan ring-1 ring-accent-cyan'
                        : 'border-border-subtle hover:border-accent-blue/50'
                    }`}
                  >
                    <img
                      src={getMediaUrl(clip.image_url)}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-black/30 flex items-end justify-between p-1 text-[9px] font-mono text-white">
                      <span>{clip.duration}s</span>
                      <span className="text-[8px] bg-black/60 px-1 rounded">{clip.motion}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Audio Track with Beat Markers */}
          <div className="h-8 bg-surface-elevated/70 rounded-lg px-2 flex items-center justify-between border border-border-subtle relative overflow-hidden">
            <span className="text-[9px] font-mono text-text-muted uppercase">AUD</span>

            {/* Visual Beat Markers */}
            {audioAnalysis && audioAnalysis.beat_times.length > 0 && (
              <div className="absolute inset-0 pointer-events-none">
                {audioAnalysis.beat_times
                  .filter(b => b <= plan.duration_seconds)
                  .map((beatTime, idx) => {
                    const leftPct = (beatTime / plan.duration_seconds) * 100;
                    const isStrong = audioAnalysis.strong_beats.includes(beatTime);
                    return (
                      <div
                        key={idx}
                        style={{ left: `${leftPct}%` }}
                        className={`absolute top-0 bottom-0 w-0.5 ${
                          isStrong ? 'bg-accent-cyan' : 'bg-accent-blue/40'
                        }`}
                        title={`Beat at ${beatTime}s`}
                      />
                    );
                  })}
              </div>
            )}

            <div className="text-[10px] font-mono text-text-secondary z-10">
              {audio ? audio.original_name : 'Default Audio Drone'}
            </div>

            <div className="text-[9px] font-mono text-accent-cyan z-10">
              {audioAnalysis ? `${audioAnalysis.tempo} BPM` : '120 BPM'}
            </div>
          </div>
        </div>
      </footer>

      {/* Render Modal */}
      {isRenderingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="max-w-md w-full bg-[#11131A] border border-border-medium rounded-3xl p-6 shadow-2xl text-center space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-accent-blue/15 border border-accent-blue/30 mx-auto flex items-center justify-center text-accent-cyan">
              {renderStatus?.status === 'completed' ? (
                <CheckCircle2 className="w-8 h-8 text-accent-cyan" />
              ) : renderStatus?.status === 'failed' ? (
                <AlertCircle className="w-8 h-8 text-red-400" />
              ) : (
                <Film className="w-8 h-8 animate-pulse text-accent-blue" />
              )}
            </div>

            <div>
              <h3 className="text-xl font-bold font-cinematic text-text-primary">
                {renderStatus?.status === 'completed'
                  ? 'Reel Export Complete!'
                  : renderStatus?.status === 'failed'
                  ? 'Export Encountered An Issue'
                  : 'Rendering Cinematic Reel'}
              </h3>
              <p className="text-xs text-text-secondary mt-1">
                {renderStatus?.status === 'completed'
                  ? 'Your high-definition 1080×1920 MP4 is ready to share.'
                  : renderStatus?.status === 'failed'
                  ? renderStatus.error || 'Failed to render reel with FFmpeg.'
                  : 'Compositing photos, Ken Burns motion, and beat-synced cuts with FFmpeg...'}
              </p>
            </div>

            {/* Progress Bar */}
            {renderStatus && renderStatus.status !== 'failed' && (
              <div className="space-y-1.5">
                <div className="w-full h-2.5 bg-surface rounded-full overflow-hidden border border-border-subtle">
                  <div
                    className="h-full bg-gradient-to-r from-accent-blue to-accent-cyan transition-all duration-300"
                    style={{ width: `${renderStatus.progress}%` }}
                  />
                </div>
                <div className="flex justify-between text-[11px] font-mono text-text-muted">
                  <span className="capitalize">{renderStatus.status}</span>
                  <span>{renderStatus.progress.toFixed(0)}%</span>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="pt-2 flex items-center justify-center gap-3">
              {renderStatus?.status === 'completed' && renderJobId && (
                <a
                  href={getDownloadUrl(renderJobId)}
                  download={`rayflow_${renderJobId}.mp4`}
                  className="px-6 py-2.5 rounded-xl bg-accent-blue hover:bg-accent-blue/90 text-white font-semibold text-xs flex items-center gap-2 shadow-lg shadow-accent-blue/30 transition-all"
                >
                  <Download className="w-4 h-4" />
                  <span>Download MP4</span>
                </a>
              )}

              <button
                onClick={() => setIsRenderingModalOpen(false)}
                className="px-4 py-2.5 rounded-xl bg-surface-elevated hover:bg-surface-hover border border-border-subtle text-text-secondary hover:text-text-primary text-xs font-medium transition-colors"
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
