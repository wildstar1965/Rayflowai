import re
import uuid
from typing import List, Dict, Optional, Any
from pathlib import Path

from app.schemas.editing_plan import VisualInsert, SubtitleSegment, ClipConfig

def extract_transcript_keywords(subtitles: List[SubtitleSegment]) -> List[Dict[str, Any]]:
    """
    Extracts meaningful nouns, subjects, and concepts with timestamps from subtitle segments.
    """
    keyword_entries: List[Dict[str, Any]] = []

    # Common stop words to filter out
    stop_words = {
        "the", "and", "a", "an", "is", "it", "to", "in", "of", "for", "on",
        "with", "as", "at", "this", "that", "i", "you", "we", "they", "my",
        "your", "our", "their", "are", "was", "were", "be", "been", "have", "has"
    }

    for seg in subtitles:
        if seg.words:
            for w in seg.words:
                clean = re.sub(r'[^a-zA-Z0-9]', '', w.word).lower()
                if clean and len(clean) >= 3 and clean not in stop_words:
                    keyword_entries.append({
                        "keyword": clean,
                        "raw_word": w.word,
                        "start_time": w.start,
                        "end_time": w.end,
                        "emphasis": w.emphasis
                    })
        else:
            tokens = re.findall(r'\b[a-zA-Z0-9]{3,}\b', seg.text.lower())
            for t in tokens:
                if t not in stop_words:
                    keyword_entries.append({
                        "keyword": t,
                        "raw_word": t,
                        "start_time": seg.start_time,
                        "end_time": seg.end_time,
                        "emphasis": False
                    })

    return keyword_entries

def suggest_contextual_inserts(
    subtitles: List[SubtitleSegment],
    available_assets: List[Dict[str, Any]],
    default_mode: str = "pip",
    max_inserts: int = 4
) -> List[VisualInsert]:
    """
    Analyzes subtitle transcript timestamps and matches available images/B-roll
    based on asset filenames, labels, and semantic keyword matching.
    Never invents nonexistent media files.
    """
    if not subtitles or not available_assets:
        return []

    keywords = extract_transcript_keywords(subtitles)
    suggested: List[VisualInsert] = []
    used_asset_urls = set()
    last_end_time = -10.0

    for kw in keywords:
        if len(suggested) >= max_inserts:
            break

        kw_text = kw["keyword"]
        # Ensure inserts don't collide or overlap too closely (at least 2.5s separation)
        if kw["start_time"] < (last_end_time + 1.5):
            continue

        # Look for matching asset
        matched_asset = None
        for asset in available_assets:
            asset_url = asset.get("url") or asset.get("filename") or ""
            if asset_url in used_asset_urls:
                continue

            asset_name = Path(asset.get("filename") or asset.get("original_name") or asset_url).stem.lower()
            asset_label = (asset.get("label") or "").lower()

            # Exact or substring match in asset filename or label
            if kw_text in asset_name or asset_name in kw_text or (asset_label and kw_text in asset_label):
                matched_asset = asset
                break

        if matched_asset:
            asset_url = matched_asset.get("url") or matched_asset.get("filename") or ""
            used_asset_urls.add(asset_url)
            start_t = round(kw["start_time"], 2)
            duration = 2.0

            suggested.append(VisualInsert(
                id=f"insert-{len(suggested) + 1}",
                asset_id=str(matched_asset.get("id", uuid.uuid4().hex[:8])),
                asset_url=asset_url,
                start_time=start_t,
                duration=duration,
                mode=default_mode,
                position="top_right",
                label=f"{kw['raw_word'].capitalize()} B-Roll"
            ))
            last_end_time = start_t + duration

    return suggested
