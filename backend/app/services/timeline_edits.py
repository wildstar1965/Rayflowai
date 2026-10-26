"""Stable-ID source-relative retiming for attached overlays and captions."""
def retime_attached(before, after):
    old = {c.id: c for c in before.clips}
    current = {c.id: c for c in after.clips}
    for collection in ('subtitles', 'transcript', 'visual_inserts', 'sound_cues', 'cinematic_texts'):
        items = []
        for item in getattr(after, collection):
            identity = item.source_clip_id
            if not identity:
                if item.start_time < after.duration_seconds:
                    if hasattr(item, 'end_time'):
                        item.end_time = min(item.end_time, after.duration_seconds)
                        item.words = [w for w in item.words if w.start < item.end_time]
                        for word in item.words:
                            word.end = min(word.end, item.end_time)
                    elif hasattr(item, 'duration'):
                        item.duration = min(item.duration, after.duration_seconds - item.start_time)
                    items.append(item)
                continue
            if identity not in current or identity not in old:
                continue
            previous, clip = old[identity], current[identity]
            delta = clip.start_time - previous.start_time - (clip.source_start - previous.source_start)
            start = item.start_time + delta
            end = (item.end_time if hasattr(item, 'end_time') else item.start_time+getattr(item,'duration',.1)) + delta
            if start >= clip.start_time+clip.duration or end <= clip.start_time:
                continue
            item.start_time = max(clip.start_time, start)
            if hasattr(item, 'end_time'):
                item.end_time = min(end,clip.start_time+clip.duration)
                for word in item.words:
                    word.start += delta; word.end += delta
                item.words = [w for w in item.words if w.end > item.start_time and w.start < item.end_time]
                for word in item.words:
                    word.start=max(word.start,item.start_time);word.end=min(word.end,item.end_time)
            elif hasattr(item,'duration'):
                item.duration=min(end,clip.start_time+clip.duration)-item.start_time
            if hasattr(item, 'behind_subject') and (previous.source_start != clip.source_start):
                item.behind_subject = False
            items.append(item)
        setattr(after, collection, items)
    return after
