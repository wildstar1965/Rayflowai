"""Compare actual Tiny/Medium inference with the saved reference transcript.

The saved ASR transcript is NOT independent human ground truth. Report agreement,
timing differences and runtime, never label agreement as transcription accuracy.
"""
import difflib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import FFMPEG_PATH
from app.services import speech_transcription as speech
from app.services.speech_models import verify_model, runtime_for

ART = ROOT / 'test_artifacts/caption-quality'
SOURCE = Path(r'C:\Users\tejar\OneDrive\Pictures\Camera Roll\WIN_20261021_16_40_31_Pro.mp4')
REFERENCE = Path(r'C:\Users\tejar\OneDrive\Desktop\New folder\caption-engine\tmp\transcript.json')


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a):
        following = [i + 1]
        for j, y in enumerate(b):
            following.append(min(row[j+1]+1, following[j]+1, row[j]+(x != y)))
        row = following
    return row[-1]


def peak_process_memory_mb():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ['PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage']]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if get_memory(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return round(counters.PeakWorkingSetSize / 1024**2, 1)
    return None


if __name__ == '__main__':
    ART.mkdir(parents=True, exist_ok=True)
    wav = ART / 'comparison-audio.wav'
    speech.extract_audio_from_media(str(SOURCE), str(wav))
    reference = json.loads(REFERENCE.read_text(encoding='utf8'))['words']
    normalize = lambda text: re.sub(r'[^\w]', '', text.casefold())
    expected = [normalize(word['text']) for word in reference]
    reports = []
    try:
        for model in ['tiny', 'medium']:
            started = time.monotonic()
            verify_model(model)
            loaded = time.monotonic()
            segments = speech._transcribe_uncached(str(wav), model, 'en')
            (ART / f'{model}-transcript.json').write_text(json.dumps([s.model_dump() for s in segments], indent=2), encoding='utf8')
            words = [word for segment in segments for word in segment.words]
            actual = [normalize(word.word) for word in words]
            deviations = []
            for a, b, size in difflib.SequenceMatcher(a=expected, b=actual, autojunk=False).get_matching_blocks():
                for i in range(size):
                    deviations.extend([abs(reference[a+i]['start']-words[b+i].start), abs(reference[a+i]['end']-words[b+i].end)])
            report = {'model': model, **runtime_for(model), 'load_and_probe_seconds': round(loaded-started, 3),
                      'inference_seconds': round(time.monotonic()-loaded, 3), 'words': len(words),
                      'reference_words': len(expected), 'word_edits_vs_saved_asr': distance(expected, actual),
                      'peak_process_working_set_mb': peak_process_memory_mb(),
                      'mean_matching_word_boundary_difference_seconds': round(sum(deviations)/len(deviations), 4) if deviations else None}
            reports.append(report)
            print(json.dumps(report), flush=True)
        (ART / 'transcription-comparison.json').write_text(json.dumps(reports, indent=2), encoding='utf8')
    finally:
        wav.unlink(missing_ok=True)
