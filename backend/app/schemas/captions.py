from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator
from app.schemas.editing_plan import SubtitleSegment


class CaptionDocument(BaseModel):
    format: Literal['rayflow-captions-v1'] = 'rayflow-captions-v1'
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    subtitles: list[SubtitleSegment] = Field(max_length=20000)

    @model_validator(mode='after')
    def valid_captions(self):
        from app.services.caption_engine import validate_captions
        self.subtitles = validate_captions(self.subtitles, self.duration_seconds)
        return self


class EngineWord(BaseModel):
    text: str = Field(max_length=500)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    type: Literal['word', 'spacing', 'audio_event'] = 'word'
    keep: bool = True
    confidence: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    speakerId: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, max_length=20)
    roman: Optional[str] = Field(default=None, max_length=500)


class EngineTranscript(BaseModel):
    words: list[EngineWord] = Field(max_length=100000)
    duration: float = Field(gt=0, allow_inf_nan=False)
    hasWordTimings: bool
    language: Optional[str] = Field(default=None, max_length=20)


class CaptionImportRequest(BaseModel):
    transcript: EngineTranscript
    media_filename: str = Field(max_length=255)
    use_roman: bool = False
