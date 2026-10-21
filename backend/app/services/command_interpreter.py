import re
import uuid
from typing import List, Optional, Tuple
from app.schemas.editing_plan import (
    EditingPlan,
    CommandRequest,
    CommandResponse,
    ClipConfig,
    TransitionConfig,
    GlobalTransitionConfig,
    SubtitleStyle
)

WORD_TO_NUM = {
    "zero": 0.0, "half": 0.5, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "eleven": 11.0, "twelve": 12.0, "fifteen": 15.0, "twenty": 20.0, "thirty": 30.0
}

ORDINAL_TO_INDEX = {
    "first": 0, "1st": 0, "1": 0, "one": 0,
    "second": 1, "2nd": 1, "2": 1, "two": 1,
    "third": 2, "3rd": 2, "3": 2, "three": 2,
    "fourth": 3, "4th": 3, "4": 3, "four": 3,
    "fifth": 4, "5th": 4, "5": 4, "five": 4,
    "sixth": 5, "6th": 5, "6": 5, "six": 5,
    "seventh": 6, "7th": 6, "7": 6, "seven": 6,
    "eighth": 7, "8th": 7, "8": 7, "eight": 7,
    "ninth": 8, "9th": 8, "9": 8, "nine": 8,
    "tenth": 9, "10th": 9, "10": 9, "ten": 9,
    "last": -1
}

def _parse_num(val_str: Optional[str]) -> Optional[float]:
    if not val_str:
        return None
    val_str = val_str.strip().lower()
    if val_str in WORD_TO_NUM:
        return WORD_TO_NUM[val_str]
    try:
        return float(val_str)
    except ValueError:
        return None

def _resolve_clip_index(word: str, clip_count: int) -> Optional[int]:
    clean = word.strip().lower()
    idx = ORDINAL_TO_INDEX.get(clean, None)
    if idx is None and clean.isdigit():
        idx = int(clean) - 1
    if idx is None:
        return None
    if idx < 0:
        idx = clip_count + idx
    if 0 <= idx < clip_count:
        return idx
    return None

def _normalize_transition_type(raw_type: str) -> str:
    clean = raw_type.lower().strip().replace("-", " ")
    if "crossfade" in clean or "dissolve" in clean:
        return "crossfade"
    if "dip to black" in clean or "fade to black" in clean or "black" in clean:
        return "dip_black"
    if "dip to white" in clean or "fade to white" in clean or "white" in clean:
        return "dip_white"
    if "fade in" in clean:
        return "fade_in"
    if "fade out" in clean:
        return "fade_out"
    if "none" in clean or "cut" in clean or "remove" in clean:
        return "none"
    return "crossfade"

def _recalc_timeline(plan: EditingPlan):
    """
    Recalculates clip start times sequentially and updates project duration.
    Also clamps boundary transitions so they do not exceed clip durations.
    """
    if plan.clips:
        curr_time = 0.0
        for clip in plan.clips:
            clip.start_time = curr_time
            curr_time += clip.duration
        plan.duration_seconds = curr_time

    # Clamp transitions safely
    if plan.transitions and len(plan.clips) > 1:
        clip_dict = {c.id: c for c in plan.clips}
        for t in plan.transitions:
            f_id = getattr(t, "from_clip_id", None) or (t.get("from_clip_id") if isinstance(t, dict) else None)
            t_id = getattr(t, "to_clip_id", None) or (t.get("to_clip_id") if isinstance(t, dict) else None)
            c1 = clip_dict.get(f_id)
            c2 = clip_dict.get(t_id)
            if c1 and c2:
                max_dur = max(0.1, min(c1.duration, c2.duration) - 0.1)
                if hasattr(t, "duration"):
                    t.duration = min(round(t.duration, 2), round(max_dur, 2))
                elif isinstance(t, dict) and "duration" in t:
                    t["duration"] = min(round(t["duration"], 2), round(max_dur, 2))

def interpret_command(request: CommandRequest, allow_llm: bool = True) -> CommandResponse:
    """
    Parses natural language video editing commands into a validated EditingPlan.
    Supports transitions, aspect ratios, fit modes, clip durations, trimming, and reordering.
    """
    if request.current_plan:
        from app.services.typed_commands import handle_typed_command
        typed = handle_typed_command(request)
        if typed is not None:
            return typed
    plan = request.current_plan.model_copy(deep=True) if request.current_plan else EditingPlan()
    text = request.command.strip()
    lower = text.lower()
    changes: List[str] = []
    clips = plan.clips
    clip_count = len(clips)

    # -------------------------------------------------------------
    # 1. Global Head & Tail Transitions
    # -------------------------------------------------------------
    # "Add a fade-in at the beginning of the entire reel"
    if re.search(r'fade[- ]?in at (?:the )?(?:beginning|start)(?: of (?:the )?(?:entire )?(?:reel|video))?', lower):
        dur_match = re.search(r'(\d+(?:\.\d+)?|one|two|three)\s*(?:seconds?|secs?|s\b)', lower)
        dur = _parse_num(dur_match.group(1)) if dur_match else 0.5
        dur = max(0.2, min(dur, 2.0))
        plan.head_transition = GlobalTransitionConfig(enabled=True, type="fade_in", duration=dur)
        changes.append(f"Added a {dur}s fade-in at the beginning of the entire reel")

    # "Fade out the video at the end"
    if re.search(r'fade[- ]?out (?:the video )?at (?:the )?(?:end|finish)(?: of (?:the )?(?:entire )?(?:reel|video))?', lower):
        dur_match = re.search(r'(\d+(?:\.\d+)?|one|two|three)\s*(?:seconds?|secs?|s\b)', lower)
        dur = _parse_num(dur_match.group(1)) if dur_match else 0.5
        dur = max(0.2, min(dur, 2.0))
        plan.tail_transition = GlobalTransitionConfig(enabled=True, type="fade_out", duration=dur)
        changes.append(f"Added a {dur}s fade-out at the end of the reel")

    # -------------------------------------------------------------
    # 2. Batch Transitions Across All Adjacent Photos
    # e.g., "Apply a 0.7-second crossfade between every adjacent photo"
    # -------------------------------------------------------------
    batch_match = re.search(
        r'(?:apply|add|set)\s+(?:a\s+)?(\d+(?:\.\d+)?|one|two|three)?[- ]?(?:second|s)?[- ]?(crossfade|dissolve|dip to black|dip to white|fade in|fade out|fade)\s+(?:transition\s+)?between (?:every|all)(?:\s+adjacent)?\s+(?:photo|clip|image)s?',
        lower
    )
    if batch_match and clip_count > 1:
        dur_raw = batch_match.group(1)
        dur = _parse_num(dur_raw) if dur_raw else 0.5
        dur = max(0.1, min(dur or 0.5, 2.0))
        t_type = _normalize_transition_type(batch_match.group(2))

        # Rebuild or update transitions list for all adjacent pairs
        new_transitions: List[TransitionConfig] = []
        for i in range(clip_count - 1):
            c_from = clips[i]
            c_to = clips[i + 1]
            max_d = max(0.1, min(c_from.duration, c_to.duration) - 0.1)
            applied_dur = min(dur, max_d)
            c_from.transition = t_type
            new_transitions.append(TransitionConfig(
                id=str(uuid.uuid4())[:8],
                from_clip_id=c_from.id,
                to_clip_id=c_to.id,
                type=t_type,
                duration=applied_dur,
                enabled=True
            ))
        plan.transitions = new_transitions
        changes.append(f"Applied a {dur}s {t_type.replace('_', ' ')} transition between every adjacent photo")

    # -------------------------------------------------------------
    # 3. Transition Between Two Specific Photos
    # e.g.:
    # - "Add a fade-in transition between the second and third photos."
    # - "Apply a crossfade between photos one and two."
    # - "Replace the transition between photos two and three with a dip to black."
    # -------------------------------------------------------------
    specific_trans_match = re.search(
        r'(?:add|apply|set|replace)\s+(?:a\s+|the\s+)?(?:(\d+(?:\.\d+)?|one|two|three)?[- ]?(?:seconds?|s)?[- ]?)?(crossfade|dissolve|dip to black|dip to white|fade[- ]?in|fade[- ]?out|fade)?\s*(?:transition\s+)?(?:between|from)\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)\s+(?:and|to)\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)(?:\s+(?:photos?|clips?|images?))?(?:\s+with\s+(?:a\s+)?(crossfade|dissolve|dip to black|dip to white|fade[- ]?in|fade[- ]?out|fade))?',
        lower
    )
    if specific_trans_match and clip_count > 1 and not batch_match:
        dur_raw = specific_trans_match.group(1)
        type_a = specific_trans_match.group(2)
        pos_a = specific_trans_match.group(3)
        pos_b = specific_trans_match.group(4)
        type_b = specific_trans_match.group(5)

        raw_type = type_b if type_b else (type_a or "crossfade")
        t_type = _normalize_transition_type(raw_type)

        idx_a = _resolve_clip_index(pos_a, clip_count)
        idx_b = _resolve_clip_index(pos_b, clip_count)

        if idx_a is not None and idx_b is not None:
            # Ensure order: left clip -> right clip
            from_idx = min(idx_a, idx_b)
            to_idx = max(idx_a, idx_b)

            if to_idx - from_idx == 1:
                c_from = clips[from_idx]
                c_to = clips[to_idx]
                dur = _parse_num(dur_raw) if dur_raw else 0.5
                max_d = max(0.1, min(c_from.duration, c_to.duration) - 0.1)
                dur = max(0.1, min(dur or 0.5, max_d, 2.0))

                # Update or insert into plan.transitions
                found = False
                for t in plan.transitions:
                    if t.from_clip_id == c_from.id and t.to_clip_id == c_to.id:
                        t.type = t_type
                        t.duration = dur
                        t.enabled = (t_type != "none")
                        found = True
                        break
                if not found:
                    plan.transitions.append(TransitionConfig(
                        id=str(uuid.uuid4())[:8],
                        from_clip_id=c_from.id,
                        to_clip_id=c_to.id,
                        type=t_type,
                        duration=dur,
                        enabled=(t_type != "none")
                    ))
                c_from.transition = t_type
                changes.append(f"Applied a {dur}s {t_type.replace('_', ' ')} transition between photo {from_idx + 1} and photo {to_idx + 1}")
            else:
                changes.append(f"Transitions can only be applied between adjacent photos (photos {idx_a + 1} and {idx_b + 1} are not adjacent)")

    # -------------------------------------------------------------
    # 4. Remove Transition Between Two Specific Photos
    # e.g., "Remove the transition between the first and second photos."
    # -------------------------------------------------------------
    remove_trans_match = re.search(
        r'remove\s+(?:the\s+)?transition\s+between\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)\s+and\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)(?:\s+(?:photos?|clips?|images?))?',
        lower
    )
    if remove_trans_match and clip_count > 1:
        pos_a = remove_trans_match.group(1)
        pos_b = remove_trans_match.group(2)
        idx_a = _resolve_clip_index(pos_a, clip_count)
        idx_b = _resolve_clip_index(pos_b, clip_count)
        if idx_a is not None and idx_b is not None:
            from_idx = min(idx_a, idx_b)
            to_idx = max(idx_a, idx_b)
            c_from = clips[from_idx]
            c_to = clips[to_idx]
            for t in plan.transitions:
                if t.from_clip_id == c_from.id and t.to_clip_id == c_to.id:
                    t.type = "none"
                    t.enabled = False
            c_from.transition = "none"
            changes.append(f"Removed transition between photo {from_idx + 1} and photo {to_idx + 1}")

    # -------------------------------------------------------------
    # 5. Remove a Specific Photo
    # e.g., "Remove the eighth photo."
    # -------------------------------------------------------------
    remove_clip_match = re.search(
        r'(?:remove|delete|drop)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)(?:\s+from\s+(?:the\s+)?timeline)?',
        lower
    )
    if remove_clip_match and clip_count > 0:
        idx = _resolve_clip_index(remove_clip_match.group(1), clip_count)
        if idx is not None:
            removed_clip = clips.pop(idx)
            def _is_unaffected(t):
                f_id = getattr(t, "from_clip_id", None) or (t.get("from_clip_id") if isinstance(t, dict) else None)
                t_id = getattr(t, "to_clip_id", None) or (t.get("to_clip_id") if isinstance(t, dict) else None)
                return f_id != removed_clip.id and t_id != removed_clip.id
            plan.transitions = [t for t in plan.transitions if _is_unaffected(t)]
            _recalc_timeline(plan)
            changes.append(f"Removed photo {idx + 1} from the timeline")
            clip_count = len(clips)

    # -------------------------------------------------------------
    # 6. Modify Transition Duration
    # e.g., "Make the transition between the third and fourth clips last one second."
    # -------------------------------------------------------------
    trans_dur_match = re.search(
        r'(?:make|set)\s+(?:the\s+)?transition\s+between\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)\s+and\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)(?:\s+(?:photos?|clips?|images?))?\s+(?:last|duration|to)?\s*(\d+(?:\.\d+)?|one|two|three)\s*(?:seconds?|secs?|s\b)?',
        lower
    )
    if trans_dur_match and clip_count > 1:
        pos_a = trans_dur_match.group(1)
        pos_b = trans_dur_match.group(2)
        dur_raw = trans_dur_match.group(3)
        idx_a = _resolve_clip_index(pos_a, clip_count)
        idx_b = _resolve_clip_index(pos_b, clip_count)
        dur = _parse_num(dur_raw)
        if idx_a is not None and idx_b is not None and dur is not None:
            from_idx = min(idx_a, idx_b)
            to_idx = max(idx_a, idx_b)
            c_from = clips[from_idx]
            c_to = clips[to_idx]
            max_d = max(0.1, min(c_from.duration, c_to.duration) - 0.1)
            dur = max(0.1, min(dur, max_d, 2.0))
            found_transition = False
            for t in plan.transitions:
                if t.from_clip_id == c_from.id and t.to_clip_id == c_to.id:
                    t.duration = dur
                    t.enabled = True
                    found_transition = True
            if not found_transition and to_idx == from_idx + 1:
                plan.transitions.append(TransitionConfig(id=f'trans-{c_from.id}-{c_to.id}',
                    from_clip_id=c_from.id, to_clip_id=c_to.id, type='crossfade', duration=dur, enabled=True))
            changes.append(f"Set transition between photo {from_idx + 1} and photo {to_idx + 1} duration to {dur}s")

    # -------------------------------------------------------------
    # 7. Fade Out Specific Photo
    # e.g., "Fade out the second photo."
    # -------------------------------------------------------------
    single_fade_match = re.search(
        r'fade\s+out\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)',
        lower
    )
    if single_fade_match and not lower.endswith("end"):
        idx = _resolve_clip_index(single_fade_match.group(1), clip_count)
        if idx is not None and idx < clip_count:
            clips[idx].transition = "fade_out"
            if idx < clip_count - 1:
                c_from = clips[idx]
                c_to = clips[idx + 1]
                found = False
                for t in plan.transitions:
                    if t.from_clip_id == c_from.id and t.to_clip_id == c_to.id:
                        t.type = "fade_out"
                        t.enabled = True
                        found = True
                        break
                if not found:
                    plan.transitions.append(TransitionConfig(
                        id=str(uuid.uuid4())[:8],
                        from_clip_id=c_from.id,
                        to_clip_id=c_to.id,
                        type="fade_out",
                        duration=0.5,
                        enabled=True
                    ))
            changes.append(f"Applied fade-out to photo {idx + 1}")

    # -------------------------------------------------------------
    # 8. Extend or Shorten Specific Photo
    # e.g., "Extend the third photo by two seconds."
    # -------------------------------------------------------------
    extend_match = re.search(
        r'(?:extend|lengthen|increase)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+by\s+(\d+(?:\.\d+)?|one|two|three|four|five)\s*(?:seconds?|secs?|s\b)?',
        lower
    )
    if extend_match and clip_count > 0:
        idx = _resolve_clip_index(extend_match.group(1), clip_count)
        delta = _parse_num(extend_match.group(2))
        if idx is not None and delta is not None and delta > 0:
            clips[idx].duration = round(clips[idx].duration + delta, 2)
            _recalc_timeline(plan)
            changes.append(f"Extended photo {idx + 1} by {delta}s (new duration: {clips[idx].duration}s)")

    shorten_match = re.search(
        r'(?:shorten|decrease|reduce)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+by\s+(\d+(?:\.\d+)?|one|two|three|four|five)\s*(?:seconds?|secs?|s\b)?',
        lower
    )
    if shorten_match and clip_count > 0:
        idx = _resolve_clip_index(shorten_match.group(1), clip_count)
        delta = _parse_num(shorten_match.group(2))
        if idx is not None and delta is not None and delta > 0:
            clips[idx].duration = max(0.5, round(clips[idx].duration - delta, 2))
            _recalc_timeline(plan)
            changes.append(f"Shortened photo {idx + 1} by {delta}s (new duration: {clips[idx].duration}s)")

    # -------------------------------------------------------------
    # 9. Set Specific Photo Duration
    # e.g., "Make the first photo last three seconds"
    # -------------------------------------------------------------
    clip_dur_match = re.search(
        r'(?:make|set)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+(?:last|to|duration)?\s*(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:seconds?|secs?|s\b)?',
        lower
    )
    if clip_dur_match and not trans_dur_match and not extend_match and not shorten_match:
        pos_str = clip_dur_match.group(1)
        dur_str = clip_dur_match.group(2)
        idx = _resolve_clip_index(pos_str, clip_count)
        dur = _parse_num(dur_str)
        if idx is not None and dur is not None and 0.5 <= dur <= 30.0 and clip_count > 0:
            clips[idx].duration = round(dur, 2)
            _recalc_timeline(plan)
            changes.append(f"Set photo {idx + 1} duration to {dur}s (total reel duration: {plan.duration_seconds}s)")

    # -------------------------------------------------------------
    # 10. Reorder / Move Clips
    # e.g., "Move the last photo to the beginning."
    #       "Move the first photo to the end."
    # -------------------------------------------------------------
    move_match = re.search(
        r'move\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+to\s+(?:the\s+)?(beginning|start|end|front|back|position\s+\d+|photo\s+\d+)',
        lower
    )
    if move_match and clip_count > 1:
        src_pos = move_match.group(1)
        dst_pos = move_match.group(2)
        src_idx = _resolve_clip_index(src_pos, clip_count)

        if dst_pos in ("beginning", "start", "front"):
            dst_idx = 0
        elif dst_pos in ("end", "back"):
            dst_idx = clip_count - 1
        else:
            num_m = re.search(r'\d+', dst_pos)
            dst_idx = int(num_m.group(0)) - 1 if num_m else None

        if src_idx is not None and dst_idx is not None and 0 <= dst_idx < clip_count and src_idx != dst_idx:
            moved_clip = clips.pop(src_idx)
            clips.insert(dst_idx, moved_clip)

            # Re-link transition configs safely to reflect new adjacent order
            new_transitions: List[TransitionConfig] = []
            for i in range(len(clips) - 1):
                c1 = clips[i]
                c2 = clips[i + 1]
                # Check if there was an existing transition between these two
                matched_t = next((t for t in plan.transitions if t.from_clip_id == c1.id and t.to_clip_id == c2.id), None)
                if matched_t:
                    new_transitions.append(matched_t)
                else:
                    new_transitions.append(TransitionConfig(
                        id=str(uuid.uuid4())[:8],
                        from_clip_id=c1.id,
                        to_clip_id=c2.id,
                        type=c1.transition if c1.transition else "none",
                        duration=0.5,
                        enabled=(c1.transition != "none")
                    ))
            plan.transitions = new_transitions
            _recalc_timeline(plan)
            changes.append(f"Moved photo {src_idx + 1} to {'beginning' if dst_idx == 0 else 'end' if dst_idx == clip_count - 1 else f'position {dst_idx + 1}'}")

    # -------------------------------------------------------------
    # 11. Aspect Ratio & Fit Mode
    # e.g., "Change the video to landscape", "Change the output ratio to square"
    # -------------------------------------------------------------
    if any(k in lower for k in ["landscape", "16:9", "horizontal"]):
        plan.aspect_ratio = "16:9"
        changes.append("Set aspect ratio to landscape (16:9)")
    elif any(k in lower for k in ["square", "1:1"]):
        plan.aspect_ratio = "1:1"
        changes.append("Set aspect ratio to square (1:1)")
    elif any(k in lower for k in ["portrait", "vertical", "9:16", "tiktok", "shorts"]):
        plan.aspect_ratio = "9:16"
        changes.append("Set aspect ratio to portrait (9:16)")

    # Fit mode detection
    if any(k in lower for k in ["fit mode to fit", "fit images", "letterbox", "pillarbox", "fit to frame"]):
        plan.fit_mode = "fit"
        changes.append("Set image fitting mode to Fit (preserve entire image with solid background)")
    elif any(k in lower for k in ["fit mode to fill", "fill screen", "crop to fill", "fill mode"]):
        plan.fit_mode = "fill"
        changes.append("Set image fitting mode to Fill (crop to fill frame)")

    # -------------------------------------------------------------
    # 12. Total Duration
    # -------------------------------------------------------------
    if not clip_dur_match and not extend_match and not shorten_match:
        dur_match = re.search(r'(\d{1,2})[-\s]*(?:seconds?|secs?|s\b)', lower)
        if dur_match and not any(k in lower for k in ["transition", "extend", "shorten"]):
            d = float(dur_match.group(1))
            if 3.0 <= d <= 60.0:
                plan.duration_seconds = d
                if clips:
                    dur_per_c = round(d / len(clips), 2)
                    for i, c in enumerate(clips):
                        if i == len(clips) - 1:
                            c.duration = round(d - (dur_per_c * (len(clips) - 1)), 2)
                        else:
                            c.duration = dur_per_c
                    _recalc_timeline(plan)
                    plan.duration_seconds = d
                changes.append(f"Set reel duration to {d}s")

    # -------------------------------------------------------------
    # 13. Pacing & Beat Sync
    # -------------------------------------------------------------
    if any(k in lower for k in ["no beat sync", "disable beat", "don't sync"]):
        plan.beat_sync = False
        changes.append("Disabled beat synchronization")
    elif any(k in lower for k in ["sync to beat", "sync cuts to beat", "beat sync", "beat-synced"]):
        plan.beat_sync = True
        changes.append("Enabled beat synchronization")

    if any(k in lower for k in ["fast cut", "faster", "rapid", "energetic"]):
        plan.cut_pacing = "fast"
        changes.append("Changed pacing to fast cuts")
    elif any(k in lower for k in ["slow cut", "slower", "gentle", "calm"]):
        plan.cut_pacing = "slow"
        changes.append("Changed pacing to slow cuts")

    # -------------------------------------------------------------
    # 14. Style Presets
    # -------------------------------------------------------------
    if "noir" in lower or "monochrome" in lower:
        plan.style = "noir"
        changes.append("Selected Film Noir style")
    elif "vintage" in lower or "retro" in lower:
        plan.style = "vintage"
        changes.append("Selected Vintage style")
    elif "vibrant" in lower or "colorful" in lower:
        plan.style = "vibrant"
        changes.append("Selected Vibrant style")
    elif "minimal" in lower:
        plan.style = "minimal"
        changes.append("Selected Minimal style")
    elif "cinematic" in lower:
        plan.style = "cinematic"
        changes.append("Selected Cinematic style")

    # -------------------------------------------------------------
    # 15. Title Text & Overlay
    # -------------------------------------------------------------
    title_match = re.search(
        r'(?:change\s+(?:the\s+)?title\s+to|set\s+(?:the\s+)?title\s+to|title\s+to|title:\s*|name\s+(?:it|reel)\s+to)\s*["\']?([^"\'.\n]+)["\']?',
        text,
        re.IGNORECASE
    )
    if title_match:
        new_title = title_match.group(1).strip()
        if new_title and len(new_title) <= 40:
            plan.title.enabled = True
            plan.title.text = new_title
            changes.append(f"Updated title to: '{plan.title.text}'")
    elif any(k in lower for k in ["no title", "remove title", "hide title", "disable title"]):
        plan.title.enabled = False
        changes.append("Disabled title overlay")
    elif any(k in lower for k in ["title at the beginning", "title at start", "beginning title", "at the beginning"]) and "title" in lower:
        plan.title.enabled = True
        plan.title.position = "center"
        changes.append("Enabled title overlay at the beginning")
    elif any(k in lower for k in ["add title", "show title", "enable title"]):
        plan.title.enabled = True
        changes.append("Enabled title overlay")

    # -------------------------------------------------------------
    # 16. Subtitle Word Emphasis
    # e.g., "Emphasize important words", "Highlight keywords"
    # -------------------------------------------------------------
    if any(k in lower for k in ["emphasize", "highlight keywords", "bold keywords", "pop keywords", "important words bigger"]):
        if plan.subtitles:
            from app.services.speech_transcription import apply_word_emphasis
            for sub in plan.subtitles:
                sub.style = sub.style or SubtitleStyle(preset="bold_pop")
                if sub.words:
                    sub.words = apply_word_emphasis(sub.words, sub.style)
            changes.append("Emphasized key high-energy words with vibrant styling in subtitles")

    # -------------------------------------------------------------
    # 17. Turn Talking-Head Video into Dynamic Reel
    # e.g., "Turn this talking-head video into a dynamic reel"
    # -------------------------------------------------------------
    if any(k in lower for k in ["dynamic reel", "talking-head", "talking head into", "auto edit reel"]):
        plan.aspect_ratio = "9:16"
        plan.style = "vibrant"
        if plan.subtitles:
            for sub in plan.subtitles:
                sub.style = sub.style or SubtitleStyle(preset="bold_pop", caption_mode="word_by_word")
                sub.style.preset = "bold_pop"
                sub.style.caption_mode = "word_by_word"
        changes.append("Optimized project as a high-energy 9:16 talking-head reel with dynamic word-by-word captions")

    # Ensure overall timeline consistency
    _recalc_timeline(plan)
    if request.current_plan:
        from app.services.timeline_edits import retime_attached
        retime_attached(request.current_plan, plan)
        if plan.model_dump() == request.current_plan.model_dump():
            changes = []

    if not changes and allow_llm:
        # Fallback to local Ollama if running
        try:
            from app.services.ollama_client import interpret_with_ollama
            ollama_res = interpret_with_ollama(text, plan)
            if ollama_res and ollama_res.applied_changes:
                return ollama_res
        except Exception as e:
            print(f"Ollama interpretation fallback deferred: {e}")

    if changes:
        explanation = f"RayFlow applied your direction: {', '.join(changes)}."
    else:
        explanation = (
            f"RayFlow could not recognize an action for '{text}'. "
            "Supported commands include:\n"
            "- 'Apply a crossfade between photos one and two'\n"
            "- 'Replace the transition between photos two and three with a dip to black'\n"
            "- 'Add a fade-in at the beginning of the entire reel'\n"
            "- 'Fade out the video at the end'\n"
            "- 'Change the video to landscape' or 'Change the output ratio to square'\n"
            "- 'Make the first photo last three seconds' or 'Extend the third photo by two seconds'\n"
            "- 'Move the last photo to the beginning'"
        )

    return CommandResponse(
        plan=plan,
        explanation=explanation,
        applied_changes=changes
    )
