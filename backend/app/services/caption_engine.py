"""Cue rules adapted from caption-engine/src/captions/group.ts to Rayflow.

Seconds remain the unit at every boundary. No ASR or renderer is duplicated.
"""
import re
from app.schemas.editing_plan import SubtitleSegment, SubtitleStyle

SENTENCE_END = re.compile(r'''[.!?।॥]['"”’)]*$''')
ABBREVIATIONS = {'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'e.g.', 'i.e.'}


def timed_words(segment):
    words = [w.model_dump() for w in segment.words if w.end > w.start and w.word.strip()]
    if re.sub(r'\s+', '', ''.join(w['word'] for w in words)) != re.sub(r'\s+', '', segment.text):
        return []
    cursor = 0
    for index, word in enumerate(words):
        at = segment.text.find(word['word'], cursor)
        gap = segment.text[cursor:at]
        word['line_before'] = '\n' in gap
        word['join_left'] = index > 0 and not gap
        cursor = at + len(word['word'])
    return words


def group_text(words):
    return ''.join(('\n' if word.get('line_before') and index else '' if not index or word.get('join_left') else ' ')
                   + word['word'] for index, word in enumerate(words))


def word_groups(words, style):
    groups, group = [], []
    for word in words:
        if group and not word.get('join_left'):
            previous = group[-1]
            sentence_end = (previous['word'].casefold() not in ABBREVIATIONS
                            and SENTENCE_END.search(previous['word']))
            if (style.caption_mode == 'word_by_word' or (not word.get('join_left') and sum(not w.get('join_left') for w in group) >= style.max_words)
                    or len(' '.join(w['word'] for w in group + [word])) > style.max_chars
                    or word['end'] - group[0]['start'] > style.max_duration
                    or word['start'] - previous['end'] >= style.gap_break
                    or sentence_end
                    or word.get('speaker_id') != previous.get('speaker_id')):
                groups.append(group)
                group = []
        group.append(word)
    if group:
        groups.append(group)
    return groups


def cue_windows(words, style, start, end):
    groups = word_groups(words, style)
    for index, group in enumerate(groups):
        begin = max(start, group[0]['start'])
        next_start = groups[index + 1][0]['start'] if index + 1 < len(groups) else end
        # Extend a flash only into available silence, never into another cue.
        finish = min(end, next_start, max(group[-1]['end'], begin + style.min_duration))
        if finish > begin:
            yield begin, finish, group


def active_word_windows(words, start, end):
    """Adapted from Caption Engine active.ts; retain highlight through ASR gaps.

    These are display windows only. Recorded word start/end values are unchanged.
    """
    for index, word in enumerate(words):
        begin = max(start, word['start'])
        stop = min(end, words[index + 1]['start'] if index + 1 < len(words) else end)
        if stop > begin:
            yield begin, stop, index


def readable_segments(segments):
    """Produce editable phrases without inventing word timings or losing text."""
    result = []
    for segment in segments:
        words = timed_words(segment)
        if not words:
            result.append(segment.model_copy(deep=True))
            continue
        style = (segment.style or SubtitleStyle()).model_copy(update={
            'caption_mode': 'phrase', 'highlight_active': True, 'safe_area': True,
        })
        for index, (start, end, group) in enumerate(cue_windows(words, style, segment.start_time, segment.end_time)):
            result.append(SubtitleSegment(
                **{**segment.model_dump(), 'id': f'{segment.id}-{index}',
                   'text': group_text(group), 'start_time': start,
                   'end_time': end, 'words': group, 'style': style.model_dump()},
            ))
    return result


def validate_captions(segments, duration):
    """Validate edited/exported documents without accepting ambiguous timing."""
    if len(segments) > 20000:
        raise ValueError('A caption document can contain at most 20,000 cues.')
    ids, previous_end = set(), 0.0
    for segment in sorted(segments, key=lambda s: s.start_time):
        if segment.id in ids:
            raise ValueError('Caption IDs must be unique.')
        ids.add(segment.id)
        if not segment.text.strip():
            raise ValueError('Caption text cannot be empty. Delete empty captions before exporting.')
        if segment.start_time < previous_end - .000001 or segment.end_time > duration + .000001:
            raise ValueError('Captions must not overlap or extend beyond the project duration.')
        cursor = segment.start_time
        for word in segment.words:
            if not word.word.strip() or word.start < cursor - .000001 or word.end <= word.start or word.end > segment.end_time + .000001:
                raise ValueError('Word timings must be ordered, positive, and inside their caption.')
            cursor = word.end
        previous_end = segment.end_time
    return sorted(segments, key=lambda s: s.start_time)
