"""The Director action registry: typed arguments shared by prompting and execution."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.editing_plan import SubtitleSegment, SubtitleStyle, WordTiming


class Params(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Empty(Params):
    pass


class Clip(Params):
    clip_id: str = Field(min_length=1, max_length=200)


class Volume(Clip):
    volume: float = Field(ge=0, le=2)


class Split(Clip):
    timestamp: float = Field(gt=0)


class Trim(Clip):
    source_start: float = Field(ge=0)
    source_end: float = Field(gt=0)
    explicit: bool = False


class Move(Clip):
    index: int = Field(ge=0, strict=True, description='Zero-based final position in the clip sequence.')


class Transform(Clip):
    rotation: float | None = Field(default=None, ge=-360, le=360, description='Clockwise degrees. Absolute unless relative=true.')
    offset_x: float | None = Field(default=None, ge=-1, le=1, description='Fraction of frame width; positive moves right, 0 is centered.')
    offset_y: float | None = Field(default=None, ge=-1, le=1, description='Fraction of frame height; positive moves down, 0 is centered.')
    relative: bool = False

    @model_validator(mode='after')
    def has_transform(self):
        if self.rotation is None and self.offset_x is None and self.offset_y is None:
            raise ValueError('Specify rotation or a position offset.')
        return self


class Ratio(Params):
    aspect_ratio: Literal['9:16', '16:9', '1:1']


class CaptionTarget(Params):
    caption_ids: list[str] = Field(default_factory=list, max_length=500)
    clip_id: str | None = None
    all: bool = False

    @model_validator(mode='after')
    def one_target(self):
        if sum((bool(self.caption_ids), bool(self.clip_id), self.all)) != 1:
            raise ValueError('Choose caption IDs, a source clip, or all captions.')
        return self


class CaptionStyle(CaptionTarget):
    style: dict = Field(description='Partial SubtitleStyle fields. Existing fields are preserved.')

    @field_validator('style')
    @classmethod
    def valid_style(cls, value):
        if not value or set(value) - set(SubtitleStyle.model_fields):
            raise ValueError('Specify supported caption style fields.')
        return SubtitleStyle.model_validate(value).model_dump(include=set(value))


class CaptionInput(Params):
    id: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    source_clip_id: str | None = None
    words: list[WordTiming] = Field(default_factory=list, max_length=1000)
    style: SubtitleStyle | None = None

    @model_validator(mode='after')
    def valid_interval(self):
        if self.end_time <= self.start_time:
            raise ValueError('Caption end must follow its start.')
        if any(w.start < self.start_time or w.end > self.end_time or w.end <= w.start for w in self.words):
            raise ValueError('Words must stay within their caption interval.')
        if any(a.end > b.start for a, b in zip(self.words, self.words[1:])):
            raise ValueError('Word timings must be ordered and non-overlapping.')
        return self


class AddCaptions(Params):
    segments: list[CaptionInput] = Field(min_length=1, max_length=500)


class Title(Params):
    text: str = Field(min_length=1, max_length=120)
    position: Literal['top', 'center', 'bottom'] = 'center'
    start_time: float | None = Field(default=None, ge=0)
    duration: float | None = Field(default=None, gt=0)
    source_clip_id: str | None = None
    color: str = Field(default='#F2E9D8', pattern=r'^#[0-9a-fA-F]{6}$')


class Transition(Params):
    type: Literal['fade_in', 'fade_out', 'crossfade', 'dip_black', 'dip_white', 'none']
    scope: Literal['head', 'tail', 'boundary'] = 'boundary'
    duration: float = Field(default=.5, ge=.1, le=2)
    from_clip_id: str | None = None
    to_clip_id: str | None = None


class Shorten(Params):
    duration_seconds: float = Field(gt=0, description='Shorten proportionally, keeping every clip in order; never extend footage.')


ACTION_REGISTRY = {
    'add_subtitles': AddCaptions, 'generate_subtitles': CaptionTarget,
    'remove_subtitles': CaptionTarget, 'style_subtitles': CaptionStyle,
    'set_aspect_ratio': Ratio, 'add_title': Title, 'remove_title': Empty,
    'add_transition': Transition, 'set_clip_volume': Volume,
    'split_clip': Split, 'trim_clip': Trim, 'move_clip': Move, 'delete_clip': Clip,
    'transform_clip': Transform,
    'shorten_video': Shorten, 'remove_silence': Clip, 'undo': Empty, 'redo': Empty,
}


def action_schemas():
    return {name: model.model_json_schema() for name, model in ACTION_REGISTRY.items()} | {
        'SubtitleStyle': SubtitleStyle.model_json_schema(), 'SubtitleSegment': SubtitleSegment.model_json_schema(),
    }
