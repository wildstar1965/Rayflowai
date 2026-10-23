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
  confidence?: number | null;
  speaker_id?: string | null;
  language?: string | null;
}

export interface TranscriptionJob {
  job_id: string;
  model?: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage?: string;
  device?: string;
  compute_type?: string;
  notice?: string;
  language?: string;
  subtitles: SubtitleSegment[];
  source_fingerprint?: string;
  error?: string;
}

export type CaptionFormat = 'srt' | 'vtt' | 'ass' | 'json';

export type SubtitlePreset = 'bold_pop' | 'fitness_energy' | 'minimalist' | 'subtle_border' | 'cinematic';

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
  font_weight?: number;
  tracking?: number;
  max_chars?: number;
  max_duration?: number;
  highlight_active?: boolean;
  active_scale?: number;
  background_opacity?: number;
  safe_area?: boolean;
  max_words?: number;
  gap_break?: number;
  min_duration?: number;
  background_color?: string;
  alignment?: 'left' | 'center' | 'right';
}

export interface SubtitleSegment {
  id: string;
  text: string;
  start_time: number;
  end_time: number;
  words?: WordTiming[];
  style?: SubtitleStyle;
  source_clip_id?: string;
  source_filename?: string;
  origin?: 'manual' | 'auto';
}

export type VisualInsertMode = 'pip' | 'split' | 'floating' | 'cutaway' | 'background';
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
  media_type?: 'image' | 'video';
  source_start?: number;
  source_clip_id?: string;
  origin?: 'manual' | 'auto';
  query?: string;
  source_page?: string;
  contributor?: string;
}

export interface SoundCue {
  id: string;
  start_time: number;
  label: string;
  sound: 'soft' | 'wood' | 'tick';
  volume: number;
  muted: boolean;
  source_clip_id?: string;
  origin?: 'manual' | 'auto';
}

export interface CinematicText {
  id: string;
  text: string;
  start_time: number;
  duration: number;
  source_clip_id: string;
  behind_subject: boolean;
  color: string;
  font_family?: 'Anton' | 'Arial' | 'DejaVu Sans';
  font_size_ratio?: number;
  font_weight?: number;
  tracking?: number;
  x?: number;
  y?: number;
  alignment?: 'left' | 'center' | 'right';
  uppercase?: boolean;
  emphasis_words?: string[];
  highlight_color?: string;
  animation_seconds?: number;
  scale_from?: number;
  origin?: 'manual' | 'auto';
}

export interface ClipConfig {
  id: string;
  image_url: string;
  start_time: number;
  duration: number;
  source_start?: number;
  source_duration?: number;
  media_type?: 'image' | 'video';
  motion: 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'static';
  transition: TransitionType;
  label?: string;
  volume?: number;
}

export interface EditingPlan {
  color_strength?: number;
  playhead_time?: number;
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
  transcript?: SubtitleSegment[];
  transcript_model?: string;
  visual_inserts?: VisualInsert[];
  sound_cues?: SoundCue[];
  cinematic_texts?: CinematicText[];
  auto_broll?: boolean;
  list_sounds?: boolean;
  music_volume?: number;
  source_filename?: string;
  source_fingerprint?: string;
  suppressed_auto_inserts?: string[];
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

export type AIActionType =
  | 'add_subtitles' | 'set_aspect_ratio' | 'add_title' | 'add_transition'
  | 'set_clip_volume' | 'split_clip' | 'trim_clip' | 'undo' | 'redo';

export interface AIAction {
  type: AIActionType;
  params: Record<string, unknown>;
}

export interface AIEditingPlan {
  explanation: string;
  actions: AIAction[];
  clarification?: string | null;
  proposed_plan: EditingPlan;
  applied_changes: string[];
}

export interface RenderJobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  output_url?: string;
  download_url?: string;
  error?: string;
  created_at: number;
}
