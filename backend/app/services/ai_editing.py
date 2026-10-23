"""OpenRouter planning and the allow-listed RayFlow action dispatcher."""

import copy
import json
import os
import re
from typing import Any, Dict, List, Tuple

import requests
from app.services.provider_settings import setting

from app.schemas.ai_editing import AIAction, AIEditingPlan
from app.schemas.editing_plan import (
    CinematicText,
    EditingPlan,
    GlobalTransitionConfig,
    SubtitleSegment,
    SubtitleStyle,
    TransitionConfig,
    WordTiming,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"
ACTION_TYPES = [
    "add_subtitles", "set_aspect_ratio", "add_title", "add_transition",
    "set_clip_volume", "split_clip", "trim_clip", "undo", "redo",
]


class AIEditingError(ValueError):
    pass


def _schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["explanation", "actions", "clarification"],
        "properties": {
            "explanation": {"type": "string"},
            "clarification": {"type": ["string", "null"]},
            "actions": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "params"],
                    "properties": {
                        "type": {"type": "string", "enum": ACTION_TYPES},
                        "params": {"type": "object"},
                    },
                },
            },
        },
    }


def _prompt(command: str, plan: EditingPlan) -> List[Dict[str, str]]:
    instructions = (
        "You are RayFlow's video editing planner. Return only the requested JSON schema. "
        "Never return code, shell commands, FFmpeg arguments, or unknown action types. "
        "Use exact clip IDs from the supplied plan. Do not trim or split unless explicitly requested. "
        "Ask for clarification instead of guessing missing clip IDs, timestamps, title text, or subtitle timings. "
        "Subtitles may include words with start/end timings and highlight emphasis. "
        "Supported actions: " + ", ".join(ACTION_TYPES) + "."
    )
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": json.dumps({
            "command": command,
            "current_plan": plan.model_dump(mode="json"),
        }, separators=(",", ":"))},
    ]


def request_plan(command: str, plan: EditingPlan) -> AIEditingPlan:
    key = setting("OPENROUTER_API_KEY").strip()
    if not key:
        raise AIEditingError("OpenRouter is not configured. Set OPENROUTER_API_KEY on the backend.")
    model = setting("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
                "X-Title": "RayFlow AI",
            },
            json={
                "model": model,
                "messages": _prompt(command, plan),
                "temperature": 0.1,
                "max_tokens": 2500,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "rayflow_editing_plan", "strict": True, "schema": _schema()},
                },
            },
            timeout=(10, 45),
        )
    except requests.Timeout as exc:
        raise AIEditingError("OpenRouter timed out. Please try again.") from exc
    except requests.RequestException as exc:
        raise AIEditingError("OpenRouter could not be reached.") from exc
    if response.status_code in (401, 403):
        raise AIEditingError("OpenRouter authentication failed. Check OPENROUTER_API_KEY.")
    if response.status_code == 429:
        raise AIEditingError("OpenRouter rate limit reached. Please wait and try again.")
    if response.status_code >= 400:
        raise AIEditingError("OpenRouter rejected the request or the selected model is unavailable.")
    try:
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError
        return AIEditingPlan.model_validate(json.loads(content))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIEditingError("OpenRouter returned a malformed editing plan.") from exc


def _clip(plan: EditingPlan, clip_id: str):
    clip = next((item for item in plan.clips if item.id == clip_id), None)
    if clip is None:
        raise AIEditingError("The requested clip does not exist in the active project.")
    return clip


def _time(value: Any, duration: float, name: str) -> float:
    if isinstance(value, bool):
        raise AIEditingError(f"{name} must be a number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AIEditingError(f"{name} must be a number.") from exc
    if result < 0 or result > duration:
        raise AIEditingError(f"{name} must be between 0 and the project duration.")
    return result


def _subtitle(params: Dict[str, Any], plan: EditingPlan) -> SubtitleSegment:
    start = _time(params.get("start_time"), plan.duration_seconds, "Subtitle start_time")
    end = _time(params.get("end_time"), plan.duration_seconds, "Subtitle end_time")
    if end <= start:
        raise AIEditingError("Subtitle end_time must be after start_time.")
    clip_id = params.get("source_clip_id")
    if clip_id is not None:
        _clip(plan, str(clip_id))
    words = [
        WordTiming.model_validate(word)
        for word in params.get("words", [])
    ]
    style = SubtitleStyle.model_validate(params["style"]) if params.get("style") else None
    return SubtitleSegment(
        id=str(params.get("id") or f"ai-subtitle-{len(plan.subtitles) + 1}"),
        text=str(params.get("text", "")).strip(),
        start_time=start,
        end_time=end,
        words=words,
        style=style,
        source_clip_id=clip_id,
        origin="auto",
    )


def apply_actions(plan: EditingPlan, ai_plan: AIEditingPlan) -> Tuple[EditingPlan, List[str]]:
    """Apply only allow-listed, validated operations to a deep copy."""
    result = copy.deepcopy(plan)
    changes: List[str] = []
    for action in ai_plan.actions:
        params = action.params
        if action.type in ("undo", "redo"):
            changes.append(f"Requested {action.type}; use the editor history controls to apply it.")
            continue
        if action.type == "set_aspect_ratio":
            ratio = params.get("aspect_ratio")
            if ratio not in ("9:16", "16:9", "1:1"):
                raise AIEditingError("Aspect ratio must be 9:16, 16:9, or 1:1.")
            result.aspect_ratio = ratio
            changes.append(f"Changed aspect ratio to {ratio}.")
        elif action.type == "set_clip_volume":
            clip = _clip(result, str(params.get("clip_id", "")))
            try:
                volume = float(params["volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AIEditingError("Clip volume must be a number.") from exc
            if not 0 <= volume <= 2:
                raise AIEditingError("Clip volume must be between 0 and 2.")
            clip.volume = volume
            changes.append(f"Set clip volume to {volume:g}.")
        elif action.type == "add_transition":
            transition_type = params.get("type")
            if transition_type not in ("fade_in", "fade_out", "crossfade", "dip_black", "dip_white", "none"):
                raise AIEditingError("Unsupported transition type.")
            scope = params.get("scope", "boundary")
            duration = max(.1, min(float(params.get("duration", .5)), 2))
            if scope == "head":
                result.head_transition = GlobalTransitionConfig(enabled=True, type=transition_type, duration=duration)
            elif scope == "tail":
                result.tail_transition = GlobalTransitionConfig(enabled=True, type=transition_type, duration=duration)
            else:
                first, second = _clip(result, str(params.get("from_clip_id", ""))), _clip(result, str(params.get("to_clip_id", "")))
                if abs(result.clips.index(first) - result.clips.index(second)) != 1:
                    raise AIEditingError("Transitions can only connect adjacent clips.")
                result.transitions = [t for t in result.transitions if not {t.from_clip_id, t.to_clip_id} == {first.id, second.id}]
                result.transitions.append(TransitionConfig(
                    id=f"ai-transition-{first.id}-{second.id}", from_clip_id=first.id, to_clip_id=second.id,
                    type=transition_type, duration=min(duration, first.duration, second.duration), enabled=transition_type != "none",
                ))
            changes.append(f"Added {transition_type.replace('_', ' ')} transition.")
        elif action.type == "add_subtitles":
            segments = params.get("segments")
            if not isinstance(segments, list) or not segments:
                raise AIEditingError("Subtitle segments with text and timings are required.")
            added = [_subtitle(segment, result) for segment in segments]
            result.subtitles.extend(added)
            changes.append(f"Added {len(added)} subtitle segment(s).")
        elif action.type == "add_title":
            text = str(params.get("text", "")).strip()
            if not text or len(text) > 120:
                raise AIEditingError("A title text is required and must be at most 120 characters.")
            result.title.text = text
            result.title.enabled = True
            if params.get("position") in ("top", "center", "bottom"):
                result.title.position = params["position"]
            if "start_time" in params or "duration" in params:
                clip_id = str(params.get("source_clip_id", ""))
                clip = _clip(result, clip_id)
                start = _time(params.get("start_time"), result.duration_seconds, "Title start_time")
                try:
                    duration = float(params.get("duration"))
                except (TypeError, ValueError) as exc:
                    raise AIEditingError("Title duration must be a number.") from exc
                if duration <= 0 or start + duration > result.duration_seconds:
                    raise AIEditingError("Title timing must stay within the project duration.")
                position = params.get("position", "center")
                result.cinematic_texts.append(CinematicText(
                    id=f"ai-title-{len(result.cinematic_texts) + 1}", text=text,
                    start_time=start, duration=duration, source_clip_id=clip.id,
                    behind_subject=False, color=params.get("color", "#F2E9D8"),
                    alignment={"top": "center", "center": "center", "bottom": "center"}.get(position, "center"),
                    y={"top": .15, "center": .5, "bottom": .85}.get(position, .5),
                    origin="auto",
                ))
            changes.append(f'Added title "{text}".')
        elif action.type in ("split_clip", "trim_clip"):
            if action.type == "trim_clip" and params.get("explicit") is not True:
                raise AIEditingError("Trimming requires an explicit trim request.")
            clip = _clip(result, str(params.get("clip_id", "")))
            if action.type == "split_clip":
                at = _time(params.get("timestamp"), clip.duration, "Split timestamp")
                if at <= 0 or at >= clip.duration:
                    raise AIEditingError("Split timestamp must be inside the clip.")
                original_duration = clip.duration
                clip.duration = at
                second = copy.deepcopy(clip)
                second.id = f"{clip.id}-split"
                second.start_time = clip.start_time + at
                second.duration = original_duration - at
                second.source_start = clip.source_start + at
                index = result.clips.index(clip)
                result.clips.insert(index + 1, second)
                changes.append(f"Split clip at {at:g}s.")
            else:
                start = _time(params.get("source_start", 0), float(clip.source_duration or clip.duration), "Trim start")
                end = _time(params.get("source_end", clip.source_start + clip.duration), float(clip.source_duration or clip.duration), "Trim end")
                if end <= start:
                    raise AIEditingError("Trim end must be after trim start.")
                clip.source_start = start
                clip.duration = end - start
                changes.append(f"Trimmed clip to {clip.duration:g}s.")
        else:
            raise AIEditingError("Unsupported AI editing action.")
    cursor = 0.0
    for clip in result.clips:
        clip.start_time = cursor
        cursor += clip.duration
    if result.clips:
        result.duration_seconds = cursor
    return result, changes
