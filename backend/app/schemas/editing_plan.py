from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator

class TitleConfig(BaseModel):
    enabled: bool = True
    text: str = "RAYFLOW"
    gradient: List[str] = ["#FFFFFF", "#CCCCCC"]
    color: str = "#FFFFFF"
    subtitle: Optional[str] = None
    position: str = "center"  # "center", "bottom", "top"

class ClipConfig(BaseModel):
    id: str
    image_url: str
    start_time: float = Field(ge=0, allow_inf_nan=False)
    duration: float = Field(gt=0, le=120, allow_inf_nan=False)
    source_start: float = Field(default=0, ge=0, allow_inf_nan=False)
    media_type: str = "image"  # "image", "video"
    motion: str = "zoom_in"  # "zoom_in", "zoom_out", "pan_left", "pan_right", "static"
    transition: str = "none"  # "none", "crossfade", "dip_black", "dip_white", "fade"
    label: Optional[str] = None
    volume: float = Field(default=1, ge=0, le=2, allow_inf_nan=False)

class WordTiming(BaseModel):
    word: str = Field(max_length=500)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    emphasis: bool = False
    color: Optional[str] = None
    size_multiplier: float = Field(default=1.0, ge=.5, le=3, allow_inf_nan=False)

class SubtitleStyle(BaseModel):
    preset: str = "bold_pop"  # "bold_pop", "fitness_energy", "minimalist", "subtle_border"
    caption_mode: str = "word_by_word"  # "word_by_word", "phrase"
    font_size: int = Field(default=42, ge=10, le=300)
    font_family: str = Field(default='Inter, sans-serif', max_length=100, pattern=r'^[\w ,.-]+$')
    color: str = Field(default='#FFFFFF',pattern=r'^#[0-9a-fA-F]{6}$')
    highlight_color: str = Field(default='#FACC15',pattern=r'^#[0-9a-fA-F]{6}$')
    stroke_color: str = Field(default='#000000',pattern=r'^#[0-9a-fA-F]{6}$')
    stroke_width: int = Field(default=3,ge=0,le=20)
    position: str = "center_bottom"  # "center_bottom", "middle", "top"
    font_weight: int = Field(default=700, ge=400, le=900)
    tracking: float = Field(default=0, ge=-2, le=15, allow_inf_nan=False)
    max_chars: int = Field(default=38, ge=10, le=100)
    max_duration: float = Field(default=4, ge=.5, le=15, allow_inf_nan=False)
    highlight_active: bool = False

class SubtitleSegment(BaseModel):
    id: str
    text: str = Field(max_length=4000)
    start_time: float = Field(ge=0, allow_inf_nan=False)
    end_time: float = Field(ge=0, allow_inf_nan=False)
    words: List[WordTiming] = Field(default_factory=list)
    style: Optional[SubtitleStyle] = None
    source_clip_id: Optional[str] = None
    source_filename: Optional[str] = None
    origin: Literal['manual', 'auto'] = 'manual'

    @model_validator(mode='after')
    def valid_interval(self):
        if self.end_time <= self.start_time:
            raise ValueError('Caption end must be after its start.')
        return self

class VisualInsert(BaseModel):
    id: str
    asset_id: str
    asset_url: str
    start_time: float = Field(ge=0, le=120, allow_inf_nan=False)
    duration: float = Field(gt=0, le=120, allow_inf_nan=False)
    mode: Literal['pip', 'split', 'floating', 'cutaway', 'background'] = "pip"
    position: Literal['top_right', 'top_left', 'bottom_right', 'right_half', 'center'] = "top_right"
    label: Optional[str] = None
    media_type: Literal['image', 'video'] = 'image'
    source_start: float = Field(default=0, ge=0, le=120, allow_inf_nan=False)
    source_clip_id: Optional[str] = None
    origin: Literal['manual', 'auto'] = 'manual'
    query: Optional[str] = None
    source_page: Optional[str] = None
    contributor: Optional[str] = None

class SoundCue(BaseModel):
    id: str
    start_time: float = Field(ge=0, le=120, allow_inf_nan=False)
    label: str
    sound: Literal['soft', 'wood', 'tick'] = 'soft'
    volume: float = Field(default=0.35, ge=0, le=1, allow_inf_nan=False)
    muted: bool = False
    source_clip_id: Optional[str] = None
    origin: Literal['manual', 'auto'] = 'auto'

class CinematicText(BaseModel):
    id: str
    text: str = Field(max_length=120)
    start_time: float = Field(ge=0, le=120, allow_inf_nan=False)
    duration: float = Field(gt=0, le=120, allow_inf_nan=False)
    source_clip_id: str
    behind_subject: bool = False
    color: str = Field(default='#F2E9D8', pattern=r'^#[0-9a-fA-F]{6}$')
    font_family: Literal['Anton', 'Arial', 'DejaVu Sans'] = 'Anton'
    font_size_ratio: float = Field(default=.15, ge=.03, le=.3, allow_inf_nan=False)
    font_weight: int = Field(default=700, ge=400, le=900)
    tracking: float = Field(default=0, ge=-2, le=15, allow_inf_nan=False)
    x: float = Field(default=.5, ge=.05, le=.95, allow_inf_nan=False)
    y: float = Field(default=.09, ge=.05, le=.85, allow_inf_nan=False)
    alignment: Literal['left', 'center', 'right'] = 'center'
    uppercase: bool = True
    emphasis_words: List[str] = Field(default_factory=list, max_length=20)
    highlight_color: str = Field(default='#E7C48C', pattern=r'^#[0-9a-fA-F]{6}$')
    animation_seconds: float = Field(default=.16, ge=0, le=1, allow_inf_nan=False)
    scale_from: float = Field(default=.97, ge=.8, le=1, allow_inf_nan=False)
    origin: Literal['manual', 'auto'] = 'manual'

class TransitionConfig(BaseModel):
    id: str
    from_clip_id: str
    to_clip_id: str
    type: str = "none"  # "none", "crossfade", "dip_black", "dip_white", "fade_in", "fade_out"
    duration: float = 0.5
    enabled: bool = True

class GlobalTransitionConfig(BaseModel):
    enabled: bool = False
    type: str = "fade"  # "fade_in", "fade_out", "dip_black", "dip_white"
    duration: float = 0.5

class EditingPlan(BaseModel):
    duration_seconds: float = Field(default=15.0, ge=0.0, le=120.0, allow_inf_nan=False)
    aspect_ratio: Literal['9:16', '16:9', '1:1'] = '9:16'
    fit_mode: Literal['fill', 'fit'] = 'fill'
    style: str = Field(default="cinematic")  # "cinematic", "vintage", "noir", "vibrant", "minimal"
    beat_sync: bool = True
    cut_pacing: str = Field(default="balanced")  # "slow", "balanced", "fast", "beat_driven"
    motion: str = Field(default="slow_zoom")  # "slow_zoom", "dynamic", "static"
    title: TitleConfig = Field(default_factory=TitleConfig)
    clips: List[ClipConfig] = Field(default_factory=list)
    transitions: List[TransitionConfig] = Field(default_factory=list)
    head_transition: Optional[GlobalTransitionConfig] = None
    tail_transition: Optional[GlobalTransitionConfig] = None
    subtitles: List[SubtitleSegment] = Field(default_factory=list)
    transcript: List[SubtitleSegment] = Field(default_factory=list)
    visual_inserts: List[VisualInsert] = Field(default_factory=list)
    sound_cues: List[SoundCue] = Field(default_factory=list)
    cinematic_texts: List[CinematicText] = Field(default_factory=list)
    auto_broll: bool = True
    list_sounds: bool = True
    music_volume: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    source_filename: Optional[str] = None
    source_fingerprint: Optional[str] = None
    suppressed_auto_inserts: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    audio_filename: Optional[str] = None


class ProjectPlanRequest(BaseModel):
    plan: Optional[EditingPlan] = None
    image_filenames: Optional[List[str]] = None
    audio_filename: Optional[str] = None

class AudioAnalysisResult(BaseModel):
    duration: float
    tempo: float
    beat_count: int
    beat_times: List[float]
    strong_beats: List[float]
    sample_rate: int

class CommandRequest(BaseModel):
    command: str
    current_plan: Optional[EditingPlan] = None
    audio_duration: Optional[float] = None
    image_count: Optional[int] = None

class CommandResponse(BaseModel):
    plan: EditingPlan
    explanation: str
    applied_changes: List[str]
    handled: bool = False

class RenderJobRequest(BaseModel):
    plan: EditingPlan
    image_filenames: List[str]
    audio_filename: Optional[str] = None

class RenderJobStatus(BaseModel):
    job_id: str
    status: str  # "queued", "processing", "completed", "failed"
    progress: float  # 0.0 to 100.0
    output_url: Optional[str] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
    created_at: float
