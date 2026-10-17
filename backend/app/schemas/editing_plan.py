from typing import List, Optional
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
    start_time: float
    duration: float
    motion: str = "zoom_in"  # "zoom_in", "zoom_out", "pan_left", "pan_right", "static"
    transition: str = "none"  # "none", "crossfade", "dip_black", "dip_white", "fade"

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
    duration_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    aspect_ratio: str = Field(default="9:16")  # "9:16", "16:9", "1:1"
    fit_mode: str = Field(default="fill")  # "fill", "fit"
    style: str = Field(default="cinematic")  # "cinematic", "vintage", "noir", "vibrant", "minimal"
    beat_sync: bool = True
    cut_pacing: str = Field(default="balanced")  # "slow", "balanced", "fast", "beat_driven"
    motion: str = Field(default="slow_zoom")  # "slow_zoom", "dynamic", "static"
    title: TitleConfig = Field(default_factory=TitleConfig)
    clips: List[ClipConfig] = Field(default_factory=list)
    transitions: List[TransitionConfig] = Field(default_factory=list)
    head_transition: Optional[GlobalTransitionConfig] = None
    tail_transition: Optional[GlobalTransitionConfig] = None

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
