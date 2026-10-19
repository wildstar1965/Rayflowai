"""Conservative spoken-list detection grounded in real word timestamps."""
import hashlib
import re
from app.schemas.editing_plan import SoundCue

ORDINALS = {'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth', 'finally'}
NUMBERS = {'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'}
INTRO = re.compile(r'\b(?:you need|we need|include|includes|such as|consist of|things:|foods are|favorites are|favourites are|are:)\b|\b(?:things|steps|items|foods|tools)\s*:', re.I)

def _sentences(words):
    """Keep a spoken sentence together even when Whisper splits its segments."""
    current = []
    for word in words:
        if current and word.start - current[-1].end > 2:
            yield current
            current = []
        current.append(word)
        if re.search(r'[.!?]$', word.word):
            yield current
            current = []
    if current:
        yield current


def detect_list_items(subtitles):
    items = []
    words = [word for segment in subtitles for word in segment.words]
    # Require two markers, and don't confuse 'one day' / 'second chance' with lists.
    markers = []
    for index, word in enumerate(words):
        token = re.sub(r'[^a-z0-9]', '', word.word.lower())
        if token in ORDINALS or ((token in NUMBERS or token.isdigit()) and re.search(r'[,.:)]$', word.word)):
            if re.search(r'[,.:)]$', word.word) or (index == 0 or re.search(r'[.!?]$', words[index-1].word)):
                markers.append(index)
    for pos, index in enumerate(markers):
        nearby = [other for other in markers if abs(words[other].start - words[index].start) <= 30]
        if len(nearby) < 2:
            continue
        end = markers[pos+1] if pos+1 < len(markers) else min(index+5, len(words))
        label = ' '.join(w.word for w in words[index+1:min(end, index+6)]).strip(' ,.')
        if label:
            items.append((words[index].start, label))
    # Comma lists must contain an explicit introduction or a final conjunction,
    # at least three short noun-like chunks, and no repeated sentence subjects.
    for sentence_words in _sentences(words):
        sentence = ' '.join(w.word for w in sentence_words)
        # A final conjunction is enough: an Oxford comma is not required.
        if len(re.findall(r',|\band\b', sentence, re.I)) < 2 or not (INTRO.search(sentence) or re.search(r'\s+and\s+', sentence, re.I)):
            continue
        intro = INTRO.search(sentence)
        body = sentence[intro.end():] if intro else sentence
        chunks = [c.strip(' .,:') for c in re.split(r',\s*(?:and\s+)?|\s+and\s+', body) if c.strip(' .,:')]
        if not 3 <= len(chunks) <= 10:
            continue
        if not intro:
            # Permit "laptop, microphone, and camera"; reject clauses.
            chunks[0] = re.sub(r'^.*?\b(?:a|an)\s+', '', chunks[0], count=1)
        if any(len(c.split()) > 5 or re.search(r'\b(?:I|we|he|she|they|because|although|when|was|were|went|said)\b', c, re.I) for c in chunks):
            continue
        cursor = 0
        matched = []
        for chunk in chunks:
            tokens = re.findall(r'\w+', chunk.lower())
            while tokens and tokens[0] in ('a', 'an', 'the', 'and'):
                tokens.pop(0)
            if not tokens:
                break
            found = None
            for index in range(cursor, len(sentence_words)):
                clean = re.sub(r'[^\w]', '', sentence_words[index].word.lower())
                if clean == tokens[0]:
                    found = index
                    break
            if found is None:
                break
            matched.append((sentence_words[found].start, chunk))
            cursor = found + len(tokens)
        if len(matched) == len(chunks):
            items.extend(matched)
    result = []
    for start, label in sorted(set(items)):
        if result and start - result[-1][0] < .18:
            continue
        result.append((start, label))
    return result

def generate_list_cues(subtitles, source_clip_id=None):
    return [SoundCue(id='list-' + hashlib.sha256(f'{source_clip_id}:{start:.3f}:{label}'.encode()).hexdigest()[:16],
                     start_time=start, label=label, source_clip_id=source_clip_id)
            for start, label in detect_list_items(subtitles)]
