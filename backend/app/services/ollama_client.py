import os
import json
import requests
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from app.schemas.editing_plan import EditingPlan, CommandRequest, CommandResponse
from app.services.provider_settings import setting, validate_host

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


class OllamaError(ValueError):
    """Safe, user-facing transport or model failure."""

    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code

class OllamaStatusResponse(BaseModel):
    available: bool
    host: str
    models: List[str] = Field(default_factory=list)
    default_model: Optional[str] = None
    error: Optional[str] = None
    ready: bool = False

class OllamaStructuredPlanUpdate(BaseModel):
    aspect_ratio: Optional[str] = None
    fit_mode: Optional[str] = None
    style: Optional[str] = None
    title_text: Optional[str] = None
    title_enabled: Optional[bool] = None
    explanation: str = "Applied local AI suggestion."
    applied_changes: List[str] = Field(default_factory=list)

def get_ollama_host() -> str:
    return validate_host(setting('OLLAMA_HOST', DEFAULT_OLLAMA_HOST))

def _local_host(host):
    # Kept as a compatibility wrapper for existing callers. Remote hosts must be
    # explicitly configured by the backend operator; redirects are never followed.
    return validate_host(host) if host else get_ollama_host()

def check_ollama_status(host: Optional[str] = None, timeout: float = 2.0) -> OllamaStatusResponse:
    """
    Checks if Ollama is running locally and queries installed models via GET /api/tags.
    Times out quickly to prevent blocking the UI when Ollama is offline.
    """
    try:
        target_host = _local_host(host)
    except ValueError as exc:
        return OllamaStatusResponse(available=False,host='local',error=str(exc))
    # Retry discovery once only for a refused/reset connection. Never retry a
    # timed-out inference (which may still be consuming resources on the server).
    for attempt in range(2):
        try:
            response = requests.get(f'{target_host}/api/tags', timeout=(timeout, timeout), allow_redirects=False)
            if response.status_code != 200:
                raise OllamaError(f'Ollama discovery returned HTTP {response.status_code}. Check the configured base URL and server access.')
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get('models'), list):
                raise OllamaError('Ollama returned an invalid model list. Check that this URL serves the Ollama API.')
            models = list(dict.fromkeys(m['name'] for m in data['models'] if isinstance(m, dict) and isinstance(m.get('name'), str) and m['name']))
            configured = setting('OLLAMA_MODEL')
            selected = configured or (models[0] if models else None)
            error = None
            if not models:
                error = 'Ollama is running but has no models. Run ollama pull qwen3:8b on the Ollama host, then reconnect.'
            elif selected not in models:
                error = 'The configured model is not installed. Select an installed model in Connections and save.'
            return OllamaStatusResponse(available=True, host=target_host, models=models, default_model=selected, ready=error is None, error=error)
        except requests.Timeout:
            error = 'Ollama discovery timed out. Check the server and network, then reconnect.'
        except requests.ConnectionError:
            if attempt == 0:
                continue
            error = 'Cannot reach Ollama from the backend. Start ollama serve on the configured host and reconnect. A cloud backend needs a reachable private Ollama server.'
        except (requests.RequestException, ValueError) as exc:
            error = str(exc) if isinstance(exc, OllamaError) else 'Ollama returned an invalid response or the connection could not be verified.'
        break
    return OllamaStatusResponse(available=False, host=target_host, error=error)


def generate_ollama(prompt, model=None, host=None, timeout=None, json_output=True, max_tokens=1024, context_size=None):
    """Validated non-streaming generation, matching Rayflow's existing protocol."""
    status = check_ollama_status(host)
    if not status.available:
        raise OllamaError(status.error)
    selected = model or status.default_model
    if not status.models:
        raise OllamaError(status.error, 422)
    if selected not in status.models:
        raise OllamaError('The selected Ollama model is not installed. Reconnect and select an installed model.', 422)
    try:
        deadline = float(timeout if timeout is not None else os.getenv('OLLAMA_GENERATION_TIMEOUT', '180'))
        if not 1 <= deadline <= 600:
            raise ValueError()
    except ValueError:
        raise OllamaError('OLLAMA_GENERATION_TIMEOUT must be between 1 and 600 seconds.') from None
    payload = {'model': selected, 'prompt': prompt, 'stream': False,
               'options': {'temperature': 0.2, 'top_p': 0.9, 'num_predict': max_tokens}}
    if selected.startswith('qwen3:'):
        payload['think'] = False
    if context_size:
        payload['options']['num_ctx'] = context_size
    if json_output:
        payload['format'] = 'json'
    try:
        response = requests.post(f'{status.host}/api/generate', json=payload,
                                 timeout=(3, deadline), allow_redirects=False)
        if response.status_code == 404:
            raise OllamaError('Ollama could not load the selected model. Reconnect and verify it is installed.', 422)
        if response.status_code != 200:
            try:
                message = str(response.json().get('error', '')).lower()
            except (ValueError, AttributeError):
                message = ''
            if any(word in message for word in ('memory', 'allocate', 'out of memory')):
                raise OllamaError('Ollama could not allocate enough memory for this model. Close memory-heavy apps or select a smaller installed model, then retry.')
            raise OllamaError(f'Ollama generation returned HTTP {response.status_code}. Check model resources and server access.')
        data = response.json()
        if (not isinstance(data, dict) or data.get('done') is not True or data.get('done_reason') == 'length' or
                not isinstance(data.get('response'), str) or not data['response'].strip()):
            raise OllamaError('Ollama did not return a completed response. Try a smaller instruction or another installed model.')
        return data['response'].strip()
    except requests.Timeout:
        raise OllamaError('Ollama generation timed out. Model loading or inference may need more memory or a longer OLLAMA_GENERATION_TIMEOUT. Retry manually.', 504) from None
    except requests.RequestException:
        raise OllamaError('Ollama disconnected during generation. Check the server and reconnect.') from None
    except ValueError as exc:
        if isinstance(exc, OllamaError):
            raise
        raise OllamaError('Ollama returned malformed JSON.') from None

def query_ollama_generate(
    prompt: str,
    model: Optional[str] = None,
    host: Optional[str] = None,
    timeout: Optional[float] = None
) -> Optional[str]:
    """
    Sends a generation prompt to Ollama with format="json" and stream=false.
    Strictly handles connection errors, timeouts, and missing models gracefully.
    """
    try:
        return generate_ollama(prompt, model, host, timeout)
    except OllamaError:
        return None

def interpret_with_ollama(
    command: str,
    current_plan: EditingPlan,
    model: Optional[str] = None,
    host: Optional[str] = None,
    strict: bool = False
) -> Optional[CommandResponse]:
    """
    Attempts to understand a complex natural language editing instruction using a local Ollama model.
    Validates all structured output against Pydantic schema before applying changes.
    Never executes arbitrary code.
    Returns None if Ollama is unavailable or response is invalid, allowing immediate fallback.
    """
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

    try:
        raw_response = generate_ollama(prompt, model=model, host=host)
    except OllamaError:
        if strict:
            raise
        return None

    try:
        parsed_dict = json.loads(raw_response)
        validated = OllamaStructuredPlanUpdate(**parsed_dict)
    except (ValueError, TypeError):
        if strict:
            raise OllamaError('The model returned an invalid editing instruction. No changes were applied.') from None
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

    if validated.title_text and (validated.title_text[:40] != new_plan.title.text or not new_plan.title.enabled):
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
