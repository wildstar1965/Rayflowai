export interface TitleConfig {
  enabled: boolean;
  text: string;
  gradient: string[];
  subtitle?: string;
  position?: 'center' | 'bottom' | 'top';
}

export interface ClipConfig {
  id: string;
  image_url: string;
  start_time: number;
  duration: number;
  motion: 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right';
  transition: 'fade' | 'crossfade' | 'cut';
}

export interface EditingPlan {
  duration_seconds: number;
  aspect_ratio: '9:16' | '16:9' | '1:1';
  style: 'cinematic' | 'vintage' | 'noir' | 'vibrant' | 'minimal';
  beat_sync: boolean;
  cut_pacing: 'slow' | 'balanced' | 'fast' | 'beat_driven';
  motion: 'slow_zoom' | 'dynamic' | 'static';
  title: TitleConfig;
  clips: ClipConfig[];
}

export interface AudioAnalysisResult {
  duration: number;
  tempo: number;
  beat_count: number;
  beat_times: number[];
  strong_beats: number[];
  sample_rate: number;
}

export interface UploadedImage {
  filename: string;
  original_name: string;
  size: number;
  url: string;
}

export interface UploadedAudio {
  filename: string;
  original_name: string;
  size: number;
  url: string;
}

export interface CommandResponse {
  plan: EditingPlan;
  explanation: string;
  applied_changes: string[];
}

export interface RenderJobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: number;
  output_url?: string;
  download_url?: string;
  error?: string;
  created_at: number;
}
