from typing import List, Optional, Literal
from pydantic import BaseModel, Field

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

class WordTiming(BaseModel):
    word: str
    start: float
    end: float
    emphasis: bool = False
    color: Optional[str] = None
    size_multiplier: float = 1.0

class SubtitleStyle(BaseModel):
    preset: str = "bold_pop"  # "bold_pop", "fitness_energy", "minimalist", "subtle_border"
    caption_mode: str = "word_by_word"  # "word_by_word", "phrase"
    font_size: int = 42
    font_family: str = "Inter, sans-serif"
    color: str = "#FFFFFF"
    highlight_color: str = "#FACC15"  # Vibrant Yellow for emphasized keywords
    stroke_color: str = "#000000"
    stroke_width: int = 3
    position: str = "center_bottom"  # "center_bottom", "middle", "top"

class SubtitleSegment(BaseModel):
    id: str
    text: str
    start_time: float
    end_time: float
    words: List[WordTiming] = Field(default_factory=list)
    style: Optional[SubtitleStyle] = None

class VisualInsert(BaseModel):
    id: str
    asset_id: str
    asset_url: str
    start_time: float
    duration: float
    mode: str = "pip"  # "pip", "split", "floating", "cutaway"
    position: str = "top_right"  # "top_right", "top_left", "right_half", "center"
    label: Optional[str] = None

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
    visual_inserts: List[VisualInsert] = Field(default_factory=list)
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
