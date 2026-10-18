import os
import json
import urllib.request
import urllib.error
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from app.schemas.editing_plan import EditingPlan, CommandRequest, CommandResponse

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

class OllamaStatusResponse(BaseModel):
    available: bool
    host: str
    models: List[str] = Field(default_factory=list)
    default_model: Optional[str] = None
    error: Optional[str] = None

class OllamaStructuredPlanUpdate(BaseModel):
    aspect_ratio: Optional[str] = None
    fit_mode: Optional[str] = None
    style: Optional[str] = None
    title_text: Optional[str] = None
    title_enabled: Optional[bool] = None
    explanation: str = "Applied local AI suggestion."
    applied_changes: List[str] = Field(default_factory=list)

def get_ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).rstrip("/")

def check_ollama_status(host: Optional[str] = None, timeout: float = 2.0) -> OllamaStatusResponse:
    """
    Checks if Ollama is running locally and queries installed models via GET /api/tags.
    Times out quickly to prevent blocking the UI when Ollama is offline.
    """
    target_host = (host or get_ollama_host()).rstrip("/")
    url = f"{target_host}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RayFlow-AI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                default_m = models[0] if models else None
                return OllamaStatusResponse(
                    available=True,
                    host=target_host,
                    models=models,
                    default_model=default_m
                )
    except Exception as e:
        return OllamaStatusResponse(
            available=False,
            host=target_host,
            models=[],
            error=str(e)
        )
    return OllamaStatusResponse(available=False, host=target_host, models=[], error="Unknown status")

def query_ollama_generate(
    prompt: str,
    model: str = "llama3.2",
    host: Optional[str] = None,
    timeout: float = 12.0
) -> Optional[str]:
    """
    Sends a generation prompt to Ollama with format="json" and stream=false.
    Strictly handles connection errors, timeouts, and missing models gracefully.
    """
    target_host = (host or get_ollama_host()).rstrip("/")
    url = f"{target_host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9
        }
    }

    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RayFlow-AI/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", None)
    except Exception as e:
        print(f"Ollama generation deferred or unavailable: {e}")
        return None

    return None

def interpret_with_ollama(
    command: str,
    current_plan: EditingPlan,
    model: Optional[str] = None,
    host: Optional[str] = None
) -> Optional[CommandResponse]:
    """
    Attempts to understand a complex natural language editing instruction using a local Ollama model.
    Validates all structured output against Pydantic schema before applying changes.
    Never executes arbitrary code.
    Returns None if Ollama is unavailable or response is invalid, allowing immediate fallback.
    """
    status = check_ollama_status(host=host, timeout=1.5)
    if not status.available or not status.models:
        return None

    selected_model = model or status.default_model or "llama3.2"
    if selected_model not in status.models and status.models:
        selected_model = status.models[0]

    prompt = f"""You are RayFlow Video Director Assistant.
A user gave this instruction: "{command}"

Current video plan:
- Duration: {current_plan.duration_seconds}s
- Aspect Ratio: {current_plan.aspect_ratio}
- Fit Mode: {current_plan.fit_mode}
- Style: {current_plan.style}
- Title: {current_plan.title.text if current_plan.title else 'None'}
- Clips count: {len(current_plan.clips)}

Return ONLY a JSON object with this schema:
{{
  "aspect_ratio": "9:16" | "16:9" | "1:1" | null,
  "fit_mode": "fill" | "fit" | null,
  "style": "cinematic" | "noir" | "vintage" | "vibrant" | "minimal" | null,
  "title_text": string | null,
  "title_enabled": boolean | null,
  "explanation": "Human readable explanation of the decision",
  "applied_changes": ["list of short changes"]
}}
"""

    raw_response = query_ollama_generate(prompt, model=selected_model, host=host)
    if not raw_response:
        return None

    try:
        parsed_dict = json.loads(raw_response)
        validated = OllamaStructuredPlanUpdate(**parsed_dict)
    except Exception as e:
        print(f"Ollama output validation error: {e}")
        return None

    # Apply strictly validated updates to a copy of the plan
    new_plan = current_plan.model_copy(deep=True)
    changes = []  # Report changes actually applied, never model claims alone.

    if validated.aspect_ratio in ("9:16", "16:9", "1:1") and validated.aspect_ratio != new_plan.aspect_ratio:
        new_plan.aspect_ratio = validated.aspect_ratio
        if not any("aspect ratio" in c.lower() for c in changes):
            changes.append(f"Set aspect ratio to {validated.aspect_ratio}")

    if validated.fit_mode in ("fill", "fit") and validated.fit_mode != new_plan.fit_mode:
        new_plan.fit_mode = validated.fit_mode
        if not any("fit" in c.lower() for c in changes):
            changes.append(f"Set fit mode to {validated.fit_mode}")

    if validated.style in ("cinematic", "noir", "vintage", "vibrant", "minimal") and validated.style != new_plan.style:
        new_plan.style = validated.style
        if not any("style" in c.lower() for c in changes):
            changes.append(f"Applied {validated.style} visual grade")

    if validated.title_text:
        new_plan.title.text = validated.title_text[:40]
        new_plan.title.enabled = True
        if not any("title" in c.lower() for c in changes):
            changes.append(f"Updated title to '{new_plan.title.text}'")

    if validated.title_enabled is not None:
        if new_plan.title.enabled != validated.title_enabled:
            changes.append('Enabled title' if validated.title_enabled else 'Disabled title')
        new_plan.title.enabled = validated.title_enabled

    if not changes:
        return None

    return CommandResponse(
        plan=new_plan,
        explanation=validated.explanation or f"Ollama applied: {', '.join(changes)}",
        applied_changes=changes
    )
