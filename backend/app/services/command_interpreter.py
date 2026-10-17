import re
from typing import List, Tuple
from app.schemas.editing_plan import EditingPlan, CommandRequest, CommandResponse

def interpret_command(request: CommandRequest) -> CommandResponse:
    """
    Parses natural language video editing commands into a validated EditingPlan.
    Preserves existing settings while applying targeted modifications.
    """
    plan = request.current_plan.model_copy(deep=True) if request.current_plan else EditingPlan()
    text = request.command.strip()
    lower = text.lower()
    changes: List[str] = []

    # 1. Duration detection (e.g., "20 seconds", "20-second", "20s", "15 sec", "duration 30")
    duration_match = re.search(r'(\d{1,2})[-\s]*(?:seconds?|secs?|s\b)', lower)
    if duration_match:
        dur = float(duration_match.group(1))
        if 3.0 <= dur <= 60.0:
            plan.duration_seconds = dur
            changes.append(f"Set reel duration to {dur}s")

    # 2. Aspect Ratio detection (e.g., "vertical", "9:16", "landscape", "16:9", "square", "1:1", "instagram reel", "tiktok")
    if any(k in lower for k in ["vertical", "9:16", "reel", "reels", "tiktok", "shorts", "story"]):
        plan.aspect_ratio = "9:16"
        changes.append("Set aspect ratio to vertical (9:16)")
    elif any(k in lower for k in ["landscape", "16:9", "horizontal", "youtube"]):
        plan.aspect_ratio = "16:9"
        changes.append("Set aspect ratio to landscape (16:9)")
    elif any(k in lower for k in ["square", "1:1", "post", "feed"]):
        plan.aspect_ratio = "1:1"
        changes.append("Set aspect ratio to square (1:1)")

    # 3. Beat synchronization
    if any(k in lower for k in ["sync to beat", "sync with beat", "match beat", "match cuts to beat", "beat sync", "beat-synced", "strong beat"]):
        plan.beat_sync = True
        changes.append("Enabled beat synchronization")
    elif any(k in lower for k in ["no beat sync", "disable beat", "don't sync", "unsync"]):
        plan.beat_sync = False
        changes.append("Disabled beat synchronization")

    # 4. Pacing detection
    if any(k in lower for k in ["fast cut", "faster", "fast pacing", "quick cut", "rapid", "energetic"]):
        plan.cut_pacing = "fast"
        changes.append("Changed pacing to fast cuts")
    elif any(k in lower for k in ["slow cut", "slower", "slow pacing", "gentle", "smooth cuts", "relax", "calm"]):
        plan.cut_pacing = "slow"
        changes.append("Changed pacing to slow cinematic cuts")
    elif any(k in lower for k in ["beat driven", "hard beat", "hit every beat", "on the beat"]):
        plan.cut_pacing = "beat_driven"
        changes.append("Changed pacing to beat-driven cuts")
    elif any(k in lower for k in ["balanced", "medium pacing", "moderate", "standard pacing"]):
        plan.cut_pacing = "balanced"
        changes.append("Changed pacing to balanced")

    # 5. Motion effects
    if any(k in lower for k in ["slow zoom", "slow zooms", "zoom in", "gentle zoom"]):
        plan.motion = "slow_zoom"
        changes.append("Applied slow cinematic zooms")
    elif any(k in lower for k in ["dynamic motion", "fast zoom", "pan and zoom", "action"]):
        plan.motion = "dynamic"
        changes.append("Applied dynamic camera motion")
    elif any(k in lower for k in ["static", "no motion", "still"]):
        plan.motion = "static"
        changes.append("Set motion to static")

    # 6. Style presets
    if "noir" in lower or "black and white" in lower or "monochrome" in lower:
        plan.style = "noir"
        changes.append("Selected Film Noir style preset")
    elif "vintage" in lower or "retro" in lower or "kodak" in lower or "analog" in lower:
        plan.style = "vintage"
        changes.append("Selected Vintage Film style preset")
    elif "vibrant" in lower or "colorful" in lower or "saturated" in lower:
        plan.style = "vibrant"
        changes.append("Selected Vibrant Cinematic style preset")
    elif "minimal" in lower or "clean" in lower:
        plan.style = "minimal"
        changes.append("Selected Minimal Editorial style preset")
    elif "cinematic" in lower or "ray" in lower or "dramatic" in lower:
        plan.style = "cinematic"
        changes.append("Selected Cinematic Director style preset")

    # 7. Title extraction
    title_quote_match = re.search(r'(?:title(?:\s+to)?|text(?:\s+to)?|call it|named)\s*["\':]?\s*([A-Za-z0-9\s!?,.-]{2,30}?)(?:["\']|\.|\s*$|\s+(?:with|and|in))', text, re.IGNORECASE)
    if title_quote_match:
        extracted_title = title_quote_match.group(1).strip().strip('"\'')
        if extracted_title and len(extracted_title) <= 30:
            plan.title.enabled = True
            plan.title.text = extracted_title.upper()
            changes.append(f"Updated title to: '{plan.title.text}'")

    if any(k in lower for k in ["no title", "remove title", "hide title", "without title"]):
        plan.title.enabled = False
        changes.append("Disabled title overlay")
    elif any(k in lower for k in ["add title", "show title", "with title", "enable title"]):
        plan.title.enabled = True
        changes.append("Enabled title overlay")

    # Title gradient colors
    if "electric-blue" in lower or "electric blue" in lower or "cyan" in lower:
        plan.title.gradient = ["#67E8F9", "#3B82F6"]
        changes.append("Applied electric-blue gradient typography")
    elif "violet" in lower or "purple" in lower:
        plan.title.gradient = ["#C084FC", "#8B5CF6"]
        changes.append("Applied vivid-violet gradient typography")
    elif "gold" in lower or "amber" in lower or "yellow" in lower:
        plan.title.gradient = ["#FDE047", "#F59E0B"]
        changes.append("Applied golden film typography")
    elif "white" in lower or "silver" in lower:
        plan.title.gradient = ["#FFFFFF", "#E2E8F0"]
        changes.append("Applied pure monochrome typography")

    if not changes:
        changes.append("Interpreted creative direction into cinematic reel settings")

    explanation = f"RayFlow applied your direction: {', '.join(changes)}."

    return CommandResponse(
        plan=plan,
        explanation=explanation,
        applied_changes=changes
    )
