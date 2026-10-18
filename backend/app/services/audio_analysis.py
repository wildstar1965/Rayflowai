import os
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import librosa
import soundfile as sf
from app.schemas.editing_plan import AudioAnalysisResult

# In-memory cache for audio analysis results
_AUDIO_CACHE: Dict[str, AudioAnalysisResult] = {}

def analyze_audio(audio_path: str) -> AudioAnalysisResult:
    """
    Analyzes an audio file using Librosa to estimate tempo, beats, and strong transients.
    """
    resolved_path = str(Path(audio_path).resolve())
    stat = Path(resolved_path).stat()
    cache_key = f"{resolved_path}:{stat.st_mtime_ns}:{stat.st_size}"
    if cache_key in _AUDIO_CACHE:
        return _AUDIO_CACHE[cache_key]

    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Audio file not found: {resolved_path}")

    # Load audio using librosa
    try:
        y, sr = librosa.load(resolved_path, sr=22050, mono=True)
    except Exception as e:
        # Fallback to soundfile if librosa default loader fails
        try:
            y, sr = sf.read(resolved_path)
            if len(y.shape) > 1:
                y = np.mean(y, axis=1)
            if sr != 22050:
                y = librosa.resample(y, orig_sr=sr, target_sr=22050)
                sr = 22050
        except Exception as sf_err:
            raise RuntimeError(f"Failed to load audio: {e} / {sf_err}")

    duration = float(librosa.get_duration(y=y, sr=sr))
    if duration <= 0:
        raise ValueError("Audio duration must be greater than zero.")

    # Beat tracking
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        # Ensure tempo is a single float value
        if isinstance(tempo, np.ndarray):
            tempo_val = float(tempo.item()) if tempo.size == 1 else float(tempo[0])
        else:
            tempo_val = float(tempo)

        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    except Exception as exc:
        raise RuntimeError(f"Beat detection failed: {exc}") from exc

    # Extract onset strength envelope to identify 'strong beats'
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        # Match onset strength to beat frames
        if len(beat_frames) > 0:
            valid_frames = [f for f in beat_frames if f < len(onset_env)]
            strengths = [onset_env[f] for f in valid_frames]
            threshold = np.median(strengths) if len(strengths) > 0 else 0.0
            strong_beats = [
                float(beat_times[i])
                for i, f in enumerate(valid_frames)
                if onset_env[f] >= threshold
            ]
        else:
            strong_beats = beat_times[::2]
    except Exception:
        strong_beats = beat_times[::2]

    result = AudioAnalysisResult(
        duration=round(duration, 3),
        tempo=round(tempo_val, 1),
        beat_count=len(beat_times),
        beat_times=[round(t, 3) for t in beat_times],
        strong_beats=[round(t, 3) for t in strong_beats],
        sample_rate=sr
    )

    if len(_AUDIO_CACHE) >= 64:
        _AUDIO_CACHE.pop(next(iter(_AUDIO_CACHE)))
    _AUDIO_CACHE[cache_key] = result
    return result
