export interface TitleConfig {
  enabled: boolean;
  text: string;
  gradient: string[];
  subtitle?: string;
  position?: 'center' | 'bottom' | 'top';
}

export type TransitionType = 'none' | 'cut' | 'crossfade' | 'dip_black' | 'dip_white' | 'fade_in' | 'fade_out';

export interface TransitionConfig {
  id: string;
  from_clip_id: string;
  to_clip_id: string;
  type: TransitionType;
  duration: number;
  enabled: boolean;
}

export interface GlobalTransitionConfig {
  enabled: boolean;
  type: 'fade_in' | 'fade_out' | 'dip_black' | 'dip_white';
  duration: number;
}

export interface WordTiming {
  word: string;
  start: number;
  end: number;
  emphasis?: boolean;
  color?: string;
  size_multiplier?: number;
}

export type SubtitlePreset = 'bold_pop' | 'fitness_energy' | 'minimalist' | 'subtle_border';

export interface SubtitleStyle {
  preset: SubtitlePreset;
  caption_mode?: 'word_by_word' | 'phrase';
  font_size: number;
  font_family: string;
  color: string;
  highlight_color: string;
  stroke_color: string;
  stroke_width: number;
  position: 'center_bottom' | 'middle' | 'top';
}

export interface SubtitleSegment {
  id: string;
  text: string;
  start_time: number;
  end_time: number;
  words?: WordTiming[];
  style?: SubtitleStyle;
}

export type VisualInsertMode = 'pip' | 'split' | 'floating' | 'cutaway';
export type VisualInsertPosition = 'top_right' | 'top_left' | 'bottom_right' | 'right_half' | 'center';

export interface VisualInsert {
  id: string;
  asset_id: string;
  asset_url: string;
  start_time: number;
  duration: number;
  mode: VisualInsertMode;
  position: VisualInsertPosition;
  label?: string;
}

export interface ClipConfig {
  id: string;
  image_url: string;
  start_time: number;
  duration: number;
  source_start?: number;
  media_type?: 'image' | 'video';
  motion: 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'static';
  transition: TransitionType;
  label?: string;
}

export interface EditingPlan {
  duration_seconds: number;
  aspect_ratio: '9:16' | '16:9' | '1:1';
  fit_mode: 'fill' | 'fit';
  style: 'cinematic' | 'vintage' | 'noir' | 'vibrant' | 'minimal';
  beat_sync: boolean;
  cut_pacing: 'slow' | 'balanced' | 'fast' | 'beat_driven';
  motion: 'slow_zoom' | 'dynamic' | 'static';
  title: TitleConfig;
  clips: ClipConfig[];
  transitions: TransitionConfig[];
  head_transition?: GlobalTransitionConfig;
  tail_transition?: GlobalTransitionConfig;
  subtitles?: SubtitleSegment[];
  visual_inserts?: VisualInsert[];
  warnings?: string[];
  audio_filename?: string | null;
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
  media_type?: 'image' | 'video';
  duration?: number;
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
