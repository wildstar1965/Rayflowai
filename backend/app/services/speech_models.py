"""Local-only Whisper discovery and inference-tested availability."""
import os
import threading
from functools import lru_cache
from pathlib import Path

INFERENCE_LOCK = threading.Lock()
_STATUS_LOCK = threading.Lock()
_CHECKING = False
_VERIFIED = {}
_RUNTIME = {}
_CPU_FALLBACK = set()
WHISPER_MODELS = ('tiny', 'base', 'small', 'medium', 'large-v3', 'turbo')
QUALITY_MODELS = ('medium', 'small', 'large-v3', 'turbo')


class TranscriptionError(RuntimeError):
    """Safe to display without native paths or credential URLs."""


def default_model():
    requested = os.getenv('WHISPER_MODEL', 'medium')
    return requested if requested in QUALITY_MODELS else 'medium'


def cached_model_path(name):
    try:
        from faster_whisper.utils import download_model
        path = Path(download_model(name, local_files_only=True))
        return path if all((path / f).is_file() for f in ('model.bin', 'config.json', 'tokenizer.json')) else None
    except Exception:
        return None


def runtime_options():
    import ctranslate2
    requested = os.getenv('WHISPER_DEVICE', 'auto').lower()
    if requested not in ('auto', 'cpu', 'cuda'):
        raise TranscriptionError('WHISPER_DEVICE must be auto, cpu or cuda.')
    device = 'cuda' if requested != 'cpu' and ctranslate2.get_cuda_device_count() > 0 else 'cpu'
    compute = os.getenv('WHISPER_COMPUTE_TYPE') or ('float16' if device == 'cuda' else 'int8')
    if device == 'cpu' and compute not in ctranslate2.get_supported_compute_types('cpu'):
        compute = 'int8'
    return device, compute


def loading_error(name, error):
    text = str(error).lower()
    if 'memory' in text or 'bad_alloc' in text or isinstance(error, MemoryError):
        return TranscriptionError(f'Not enough memory to load {name}. Close other model processes or explicitly cache and select Small; no smaller model was substituted.')
    return TranscriptionError(f'Local Whisper {name} could not load. Verify the cached model with backend/setup_local_assets.py --whisper {name}; use WHISPER_DEVICE=cpu and WHISPER_COMPUTE_TYPE=int8 if the GPU runtime is unavailable.')


@lru_cache(maxsize=1)
def load_model(name, device='auto', compute_type=None):
    # This function runs only on a cache miss. Release the previous cached model
    # before allocating the next, rather than briefly holding two large models.
    load_model.cache_clear()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise TranscriptionError('Install speech recognition with python -m pip install -r backend/requirements.txt') from None
    selected, compute = runtime_options() if device == 'auto' else (device, compute_type or ('int8' if device == 'cpu' else 'float16'))
    compute = compute_type or compute
    notice = ''
    if device == 'auto' and name in _CPU_FALLBACK:
        selected, compute = 'cpu', 'int8'
        notice = 'GPU runtime failed its check; using the same model on CPU/int8. Processing will be slower.'
    elif selected == 'cpu' and os.getenv('WHISPER_DEVICE') == 'cuda':
        notice = 'No compatible CUDA device was detected; using the same model on CPU/int8.'
    try:
        model = WhisperModel(name, device=selected, compute_type=compute, local_files_only=True)
        _RUNTIME[name] = {'device': selected, 'compute_type': compute, 'notice': notice}
        return model
    except Exception as error:
        if selected == 'cuda':
            _CPU_FALLBACK.add(name)
            try:
                model = WhisperModel(name, device='cpu', compute_type='int8', local_files_only=True)
                _RUNTIME[name] = {'device': 'cpu', 'compute_type': 'int8', 'notice': 'GPU loading failed; using the same model on CPU/int8. Processing will be slower.'}
                return model
            except Exception as fallback_error:
                raise loading_error(name, fallback_error) from None
        raise loading_error(name, error) from None


def runtime_for(name):
    return dict(_RUNTIME.get(name, {}))


def verify_model(name):
    import numpy as np
    model = load_model(name)
    try:
        segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language='en', beam_size=1,
                                      vad_filter=False, condition_on_previous_text=False)
        list(segments)  # CUDA errors can occur at encode, not model construction.
    except Exception as error:
        if runtime_for(name).get('device') != 'cuda':
            raise loading_error(name, error) from None
        load_model.cache_clear()
        _CPU_FALLBACK.add(name)
        del model
        model = load_model(name, 'cpu', 'int8')
        try:
            segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language='en', beam_size=1, vad_filter=False)
            list(segments)
        except Exception as fallback_error:
            raise loading_error(name, fallback_error) from None
        _RUNTIME[name]['notice'] = 'GPU inference failed; the same model is verified on CPU/int8. Processing will be slower.'
    return runtime_for(name)


def model_catalog():
    with _STATUS_LOCK:
        checked, checking = dict(_VERIFIED), _CHECKING
    rows = []
    for name in QUALITY_MODELS:
        cached = cached_model_path(name) is not None
        state = checked.get(name, {}) if cached else {}
        rows.append({'id': name, 'label': {'large-v3': 'Large v3', 'turbo': 'Large v3 Turbo'}.get(name, name.title()),
                     'status': state.get('status', 'checking' if cached and checking else 'unverified' if cached else 'missing'),
                     'message': state.get('message', 'Check local model' if cached else f'Not cached. Run backend/setup_local_assets.py --whisper {name}.'),
                     **state.get('runtime', {})})
    preferred = default_model()
    ready = [row['id'] for row in rows if row['status'] == 'ready']
    selected = preferred if preferred in ready else next(iter(ready), None)
    return {'models': rows, 'checking': checking, 'default_model': selected,
            'notice': f'{preferred} is unavailable; {selected} is the verified alternative.' if selected and selected != preferred else '',
            'performance': 'CPU inference can take longer than the video; progress follows processed speech. Models are checked locally without downloads.'}


def start_model_check():
    global _CHECKING
    with _STATUS_LOCK:
        if _CHECKING:
            return
        _CHECKING = True
    def worker():
        global _CHECKING
        try:
            for name in QUALITY_MODELS:
                if cached_model_path(name) is None:
                    continue
                with _STATUS_LOCK:
                    if _VERIFIED.get(name, {}).get('status') == 'ready':
                        continue
                    _VERIFIED[name] = {'status': 'checking', 'message': f'Checking {name} with local inference…'}
                try:
                    with INFERENCE_LOCK:
                        runtime = verify_model(name)
                    state = {'status': 'ready', 'message': f"Verified on {runtime['device']}/{runtime['compute_type']}", 'runtime': runtime}
                except Exception as error:
                    state = {'status': 'failed', 'message': str(error) if isinstance(error, TranscriptionError) else 'Model verification failed. Check speech dependencies.'}
                with _STATUS_LOCK:
                    _VERIFIED[name] = state
        finally:
            with _STATUS_LOCK:
                _CHECKING = False
    threading.Thread(target=worker, daemon=True).start()
