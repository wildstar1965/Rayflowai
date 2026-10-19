"""Local recurrent video matting, with optional U2Net human-mask support."""
import hashlib
import json
import os
import subprocess
import threading
import tempfile
import shutil
import time
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from app.core.config import BASE_DIR, CACHE_DIR, FFMPEG_PATH
from app.services.media import uploaded_path, probe_media
from app.services.processing import check_cancel

_lock = threading.Lock()

def model_path():
    value = os.getenv('PERSON_SEGMENTATION_MODEL', '')
    default = BASE_DIR / 'models/rvm_mobilenetv3_fp32.onnx'
    if not default.is_file(): default = BASE_DIR / 'models/u2net_human_seg.onnx'
    path = Path(value) if value else default
    if not path.is_absolute():
        path = BASE_DIR.parent / path
    return path

def availability():
    import importlib.util
    ready = model_path().is_file() and importlib.util.find_spec('onnxruntime') is not None
    return {'available': ready, 'message': 'Local person segmentation ready.' if ready else
            'Text-behind-speaker needs a local RVM or U2Net person model and onnxruntime. Run backend/setup_local_assets.py --video-matting. Regular typography remains available.'}

@lru_cache(maxsize=1)
def _session(path, stamp):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    requested = os.getenv('PERSON_SEGMENTATION_PROVIDER', 'CPUExecutionProvider')
    providers = [requested, 'CPUExecutionProvider'] if requested in ort.get_available_providers() and requested != 'CPUExecutionProvider' else ['CPUExecutionProvider']
    return ort.InferenceSession(path, sess_options=opts, providers=providers)

def processing_sizes():
    try:
        return (max(320, min(1920, int(os.getenv('PERSON_MASK_MAX_SIDE', '960')))),
                max(320, min(1920, int(os.getenv('PERSON_INFERENCE_MAX_SIDE', '960')))))
    except ValueError:
        raise ValueError('PERSON_MASK_MAX_SIDE and PERSON_INFERENCE_MAX_SIDE must be integer pixel sizes.') from None

def mask_duration(plan, clip):
    ends = [t.start_time + t.duration - clip.start_time for t in plan.cinematic_texts if t.source_clip_id == clip.id]
    ends += [i.start_time+i.duration-clip.start_time for i in plan.visual_inserts if i.mode=='background'
             and clip.start_time<=i.start_time<clip.start_time+clip.duration]
    return min(clip.duration, max(ends)) if ends else clip.duration

def mask_key(clip, ratio, fit_mode, duration=None):
    path = uploaded_path(clip.image_url)
    model = model_path()
    # Pydantic defaults may be integers while JSON round-trips produce floats.
    # Canonicalize numeric values so browser/API/export share the cache key.
    data = ['person-v3', path.name, path.stat().st_mtime_ns, path.stat().st_size, processing_sizes(),
            round(float(clip.source_start),6), round(float(duration or clip.duration),6), ratio, fit_mode,
            model.name, model.stat().st_mtime_ns if model.exists() else 0]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()

def prepare_masks(clip, ratio, fit_mode, duration=None, progress=None, cancel=None):
    cancel = cancel or getattr(progress, 'cancel', None)
    check_cancel(cancel)
    if not availability()['available']:
        raise ValueError(availability()['message'])
    path = uploaded_path(clip.image_url)
    if clip.media_type != 'video':
        raise ValueError('Subject segmentation requires a video clip.')
    key = mask_key(clip, ratio, fit_mode, duration)
    directory = CACHE_DIR / f'matte_{key}'
    manifest = directory / 'ready.json'
    while not _lock.acquire(timeout=.1):
        check_cancel(cancel)
    temporary = None
    started = time.monotonic()
    try:
        check_cancel(cancel)
        if manifest.exists():
            return json.loads(manifest.read_text())
        native_key = mask_key(clip, 'source', 'source', duration)
        native_directory = None
        for candidate in CACHE_DIR.glob('matte_*/ready.json'):
            try:
                cached = json.loads(candidate.read_text())
                original = CACHE_DIR / f"matte_{cached.get('native_directory', '')}"
                if cached.get('native_key') == native_key and (original/'source_00000.png').is_file():
                    native_directory = original
                    break
            except (OSError, ValueError):
                continue
        temporary = Path(tempfile.mkdtemp(prefix='matte_work_', dir=CACHE_DIR))
        info = probe_media(path)
        source_w, source_h = info.get('width', 320), info.get('height', 320)
        if not source_w or not source_h:
            raise ValueError('Source video dimensions could not be read.')
        max_side, inference_side = processing_sizes()
        rw, rh = {'9:16': (9,16), '16:9': (16,9), '1:1': (1,1)}[ratio]
        width, height = round(max_side*rw/max(rw,rh)/2)*2, round(max_side*rh/max(rw,rh)/2)*2
        frames = max(1, round((duration or clip.duration)*30))
        session = _session(str(model_path()), model_path().stat().st_mtime_ns)
        recurrent = session.get_inputs()[0].name == 'src'
        decode_w = max(32,round(source_w/max(source_w,source_h)*inference_side/2)*2) if recurrent else 320
        decode_h = max(32,round(source_h/max(source_w,source_h)*inference_side/2)*2) if recurrent else 320
        decoder = None if native_directory else subprocess.Popen([FFMPEG_PATH, '-v','error','-nostdin','-ss',str(clip.source_start),'-i',str(path),
            '-vf',f'fps=30,scale={decode_w}:{decode_h},tpad=stop_mode=clone:stop_duration={clip.duration}',
            '-frames:v',str(frames),'-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        input_name = session.get_inputs()[0].name
        previous = None
        recurrent_state = {f'r{i}i':np.zeros((1,1,1,1),np.float32) for i in range(1,5)}
        try:
            for index in range(frames):
                check_cancel(cancel)
                if native_directory:
                    with Image.open(native_directory/f'source_{index:05d}.png') as cached_mask:
                        mask = cached_mask.copy()
                else:
                    raw = decoder.stdout.read(decode_w*decode_h*3)
                    if len(raw) != decode_w*decode_h*3:
                        raise ValueError('Source decoding ended before the requested subject-mask frame.')
                    array = np.frombuffer(raw,np.uint8).reshape(decode_h,decode_w,3).astype(np.float32)
                    if recurrent:
                        tensor = (array/255).transpose(2,0,1)[None].astype(np.float32)
                        outputs = session.run(None, {'src':tensor,**recurrent_state,'downsample_ratio':np.array([.5],np.float32)})
                        prediction = np.clip(outputs[1][0,0],0,1)
                        recurrent_state = {f'r{i+1}i':outputs[i+2] for i in range(4)}
                    else:
                        array /= max(float(array.max()), 1)
                        tensor = ((array - [.485,.456,.406]) / [.229,.224,.225]).transpose(2,0,1)[None].astype(np.float32)
                        prediction = session.run(None, {input_name: tensor})[0][0,0]
                        prediction = (prediction-prediction.min()) / max(float(prediction.max()-prediction.min()), 1e-6)
                    if previous is not None and not recurrent:
                        prediction = .9*prediction + .1*previous
                    previous = prediction
                    mask = Image.fromarray((prediction*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(.4))
                    mask.save(temporary/f'source_{index:05d}.png')
                scale = (max if fit_mode == 'fill' else min)(width/source_w,height/source_h)
                resized = mask.resize((max(1,round(source_w*scale)), max(1,round(source_h*scale))),Image.Resampling.BILINEAR)
                frame = Image.new('L',(width,height));frame.paste(resized,((width-resized.width)//2,(height-resized.height)//2))
                frame.save(temporary/f'{index:05d}.png')
                if progress and (index%15==0 or index==frames-1):
                    progress(f'Preparing person masks: {index+1}/{frames} frames')
            if decoder:
                decoder.stdout.close()
                decoder.wait(timeout=10)
                if decoder.returncode:
                    raise ValueError('Source decoding failed while preparing the person masks.')
            check_cancel(cancel)
            result = {'key':key,'fps':30,'frames':frames,'width':width,'height':height,
                      'native_key':native_key,'native_directory':native_directory.name[6:] if native_directory else key,
                      'reused_inference':bool(native_directory),
                      'source_start':clip.source_start,'duration':frames/30,
                      'elapsed_seconds':round(time.monotonic()-started,3),
                      'url_template':f'/api/cinematic/masks/{key}/{{frame}}.png'}
            (temporary/'ready.json').write_text(json.dumps(result))
            if directory.exists():
                # Only an unpublished cache from a previously interrupted run.
                if directory.resolve().parent != CACHE_DIR.resolve() or (directory/'ready.json').exists():
                    raise ValueError('Subject cache changed while preparing masks. Retry preparation.')
                shutil.rmtree(directory)
            temporary.replace(directory)
            return result
        finally:
            if decoder and decoder.poll() is None:
                decoder.kill();decoder.wait()
            if decoder and decoder.stdout:
                decoder.stdout.close()
    finally:
        if temporary is not None and temporary.exists() and temporary.resolve().parent == CACHE_DIR.resolve():
            shutil.rmtree(temporary)
        _lock.release()

def existing_masks(clip, ratio, fit_mode, duration=None):
    key = mask_key(clip, ratio, fit_mode, duration)
    directory = CACHE_DIR / f'matte_{key}'
    if not (directory/'ready.json').exists():
        raise ValueError('Prepare the subject mask for this clip and framing before using text-behind-speaker.')
    return directory
