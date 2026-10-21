"""Conservative, reversible source trims using word times AND recorded silence."""
import math
import re
import wave
import numpy as np
from app.schemas.editing_plan import ClipConfig


def quiet_windows(wav_path):
    with wave.open(str(wav_path), 'rb') as wav:
        if wav.getsampwidth() != 2:
            return []
        rate, channels = wav.getframerate(), wav.getnchannels()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), '<i2').astype(float)/32768
    samples = samples.reshape(-1, channels).mean(axis=1)
    hop = max(1, round(rate*.02))
    blocks = samples[:len(samples)//hop*hop].reshape(-1, hop)
    if not len(blocks):
        return []
    rms = np.sqrt(np.mean(blocks**2, axis=1))
    noise, speech = np.percentile(rms, [10, 75])
    # Allow steady room tone, but require clear separation from typical speech.
    if speech <= noise*2:
        return []
    threshold = min(.025, max(.003, float(noise)*1.5), float(speech)*.4)
    return [(i*hop/rate, (i+1)*hop/rate) for i, level in enumerate(rms) if level < threshold]


def speech_clips(filename, duration, segments, quiet):
    """Never reorder speech or cut on estimated segment-only word boundaries."""
    def original():
        return [ClipConfig(id='clip-main-1', image_url=f'/api/uploads/{filename}', start_time=0,
                           duration=duration, media_type='video', motion='static', label=filename)]
    # Missing/partial timestamps cannot safely establish where a word ends.
    if not segments or any(not s.words or re.sub(r'\s+', '', s.text) !=
                           re.sub(r'\s+', '', ''.join(w.word for w in s.words)) for s in segments):
        return original()
    words = sorted([w for s in segments for w in s.words], key=lambda w:w.start)
    if any(w.end <= w.start for w in words) or any(a.end > b.start+.04 for a,b in zip(words,words[1:])):
        return original()

    def silent(start,end):
        return end > start and sum(max(0,min(end,b)-max(start,a)) for a,b in quiet)/(end-start) >= .85

    start, end = 0.0, duration
    # Remove only a standalone greeting. Retain names, qualifications and context.
    if len(words)>3 and re.fullmatch(r'(?:hi|hello|hey)[,!.]?',words[0].word.strip(),re.I) and words[0].end<=1:
        start = max(words[0].end+.04,words[1].start-.12)
    elif words[0].start>.45 and silent(0,words[0].start-.12):
        start = max(0,words[0].start-.15)
    if duration-words[-1].end>.65 and silent(words[-1].end+.2,duration-.04):
        end = min(duration,words[-1].end+.3)
    spans=[]
    for left,right in zip(words,words[1:]):
        if len(spans)>=23:
            break
        if right.start-left.end>=1 and left.end-start>=.8 and silent(left.end+.2,right.start-.2):
            spans.append((start,left.end+.24))
            start=right.start-.2
    spans.append((start,end))
    clips=[];tick=0
    for begin,finish in spans:
        # Round outwards so padding protects consonants; all timeline cuts are frame ticks.
        first=max(0,math.floor(begin*30));last=min(math.floor(duration*30),math.ceil(finish*30))
        if last-first<1:
            continue
        clips.append(ClipConfig(id=f'clip-main-{len(clips)+1}',image_url=f'/api/uploads/{filename}',
            source_start=first/30,start_time=tick/30,duration=(last-first)/30,media_type='video',
            motion='static',label=filename))
        tick+=last-first
    return clips if tick>=30 else original()
