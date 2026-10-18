import os
import sys
import time
import wave
import struct
import math
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import UPLOAD_DIR
from app.schemas.editing_plan import WordTiming, SubtitleStyle
from app.services.speech_transcription import (
    extract_audio_from_media,
    apply_word_emphasis,
    start_transcription_job,
    get_transcription_job
)

def create_synthetic_voice_sample(path: Path, duration: float = 2.5):
    """Creates a test WAV file with audible frequency pulses."""
    sample_rate = 16000
    n_samples = int(duration * sample_rate)
    with wave.open(str(path), 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            # 220Hz + 440Hz harmonic voice simulation
            s = 0.5 * math.sin(2 * math.pi * 220 * t) + 0.3 * math.sin(2 * math.pi * 440 * t)
            val = int(s * 16000)
            wav.writeframesraw(struct.pack('<h', max(-32768, min(32767, val))))

def test_word_emphasis_detection():
    print("Testing word emphasis detection rules...")
    style = SubtitleStyle(preset="bold_pop", highlight_color="#FACC15")
    words = [
        WordTiming(word="The", start=0.0, end=0.2),
        WordTiming(word="PROTEIN", start=0.2, end=0.7),  # All caps + keyword
        WordTiming(word="diet", start=0.7, end=0.9),     # Keyword
        WordTiming(word="gives", start=0.9, end=1.1),
        WordTiming(word="10X", start=1.1, end=1.4),       # Number / metric
        WordTiming(word="results", start=1.4, end=1.8),   # Keyword
    ]

    emphasized = apply_word_emphasis(words, style)
    emp_map = {w.word: w.emphasis for w in emphasized}

    assert emp_map["PROTEIN"] is True, "PROTEIN should be emphasized"
    assert emp_map["diet"] is True, "diet should be emphasized"
    assert emp_map["10X"] is True, "10X should be emphasized"
    assert emp_map["results"] is True, "results should be emphasized"
    assert emp_map["The"] is False, "'The' should not be emphasized"
    assert emp_map["gives"] is False, "'gives' should not be emphasized"
    print("   [OK] Word emphasis rules passed!")

def test_transcription_pipeline():
    print("Testing audio extraction and transcription worker pipeline...")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    test_audio = UPLOAD_DIR / "speech_test_sample.wav"
    create_synthetic_voice_sample(test_audio, duration=2.0)

    # Test audio extraction helper
    extracted_wav = UPLOAD_DIR / "speech_extracted_test.wav"
    extract_audio_from_media(str(test_audio), str(extracted_wav))
    assert extracted_wav.exists() and extracted_wav.stat().st_size > 1000
    print("   [OK] Audio extraction via FFmpeg passed!")

    # Start async transcription job (uses 'tiny' model for fast test execution)
    job_id = start_transcription_job(test_audio.name, model_size="tiny")
    print(f"   Started transcription job: {job_id}")

    for _ in range(60):
        job = get_transcription_job(job_id)
        assert job is not None
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    final_job = get_transcription_job(job_id)
    assert final_job["status"] == "completed", f"Job failed: {final_job.get('error')}"
    assert final_job["progress"] == 100.0
    print(f"   [OK] Transcription completed successfully with {len(final_job['subtitles'])} segments!")

if __name__ == "__main__":
    test_word_emphasis_detection()
    test_transcription_pipeline()
    print("\nALL SPEECH RECOGNITION TESTS PASSED SUCCESSFULLY!")
