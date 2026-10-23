"""Provider, sound and transcript-aware editing endpoints."""
from typing import Literal
import threading
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.core.config import ASSET_DIR
from app.core.config import CACHE_DIR
from app.schemas.editing_plan import EditingPlan, VisualInsert
from app.services import pixabay
from app.services.broll import regenerate_broll
from app.services.list_sounds import generate_list_cues

router = APIRouter(prefix='/api')
_alpha_lock = threading.Lock()

@router.get('/broll/search')
def search_broll(q: str, kind: Literal['image', 'video'] = 'image', aspect_ratio: Literal['9:16', '16:9', '1:1'] = '9:16'):
    try:
        return {'results': pixabay.search(q, kind, aspect_ratio), 'provider': 'Pixabay'}
    except pixabay.MediaProviderError as exc:
        raise HTTPException(503, str(exc)) from None

class SelectAsset(BaseModel):
    plan: EditingPlan
    asset_id: int = Field(gt=0)
    kind: Literal['image', 'video']
    replace_id: str | None = None
    start_time: float = Field(default=0, ge=0)
    duration: float = Field(default=2.5, gt=0)

@router.post('/broll/select', response_model=EditingPlan)
def select_asset(req: SelectAsset):
    import uuid
    plan = req.plan.model_copy(deep=True)
    previous = next((i for i in plan.visual_inserts if i.id == req.replace_id), None)
    if req.replace_id and not previous:
        raise HTTPException(404, 'The insert to replace no longer exists.')
    start = previous.start_time if previous else req.start_time
    duration = min(previous.duration if previous else req.duration, plan.duration_seconds - start)
    if duration <= 0:
        raise HTTPException(400, 'Place the insert within the project timeline.')
    try:
        asset = pixabay.download(req.asset_id, req.kind)
    except (pixabay.MediaProviderError, OSError) as exc:
        raise HTTPException(503, str(exc) if isinstance(exc, pixabay.MediaProviderError) else 'Could not save media.') from None
    if previous:
        insert = previous.model_copy(deep=True)
    else:
        insert = VisualInsert(id='insert-' + uuid.uuid4().hex[:16], asset_id=str(req.asset_id),
                              asset_url=asset['url'], start_time=start, duration=duration)
    insert.asset_id = str(req.asset_id)
    insert.asset_url = asset['url']
    insert.media_type = req.kind
    insert.source_page = asset['source_page']
    insert.contributor = asset['contributor']
    insert.label = asset['tags'][:80]
    insert.origin = 'manual'
    insert.source_start = 0
    insert.duration = min(duration, asset['duration']) if req.kind == 'video' else duration
    plan.visual_inserts = [i for i in plan.visual_inserts if i.id != insert.id] + [insert]
    return plan

@router.post('/broll/regenerate', response_model=EditingPlan)
def regenerate(plan: EditingPlan):
    return regenerate_broll(plan)

@router.post('/sounds/detect', response_model=EditingPlan)
def detect_sounds(plan: EditingPlan):
    updated = plan.model_copy(deep=True)
    existing = {cue.id: cue for cue in updated.sound_cues}
    fresh = generate_list_cues(updated.subtitles)
    updated.sound_cues = list(existing.values()) + [cue for cue in fresh if cue.id not in existing
        and not any(abs(old.start_time - cue.start_time) < .18 for old in existing.values())]
    updated.list_sounds = True
    return updated

@router.get('/sounds/{name}.wav')
def sound_asset(name: Literal['soft', 'wood', 'tick']):
    return FileResponse(ASSET_DIR / 'sounds' / f'{name}.wav', media_type='audio/wav')

@router.get('/creative/jobs/{job_id}')
def creative_status(job_id: str):
    from app.editor.context import workspace_id
    from app.services import job_history
    if workspace_id.get() and not job_history.get(job_id):
        raise HTTPException(404, 'Processing job not found.')
    from app.services.creative_jobs import JOBS
    if job_id not in JOBS:
        raise HTTPException(404, 'Processing job not found. The backend may have restarted.')
    return JOBS[job_id]

@router.post('/creative/jobs/{job_id}/cancel')
def cancel_creative_job(job_id: str):
    from app.services.creative_jobs import cancel_job
    if not cancel_job(job_id):
        raise HTTPException(409, 'This processing job is no longer active.')
    return {'status': 'cancelled'}

@router.get('/cinematic/status')
def cinematic_status():
    from app.services.segmentation import availability
    return availability()

class MaskRequest(BaseModel):
    plan: EditingPlan
    clip_id: str

@router.post('/cinematic/prepare')
def prepare_subject(req: MaskRequest):
    from app.services.segmentation import prepare_masks, availability, mask_duration
    from app.services.creative_jobs import start_job
    clip = next((c for c in req.plan.clips if c.id == req.clip_id), None)
    if not clip or clip.media_type != 'video':
        raise HTTPException(400, 'Select a video clip for subject masking.')
    if not availability()['available']:
        raise HTTPException(503, availability()['message'])
    def work(report):
        report('Computing local person masks')
        return prepare_masks(clip, req.plan.aspect_ratio, req.plan.fit_mode, mask_duration(req.plan, clip), progress=report)
    try:
        return {'job_id': start_job(work)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

@router.post('/cinematic/matte')
def get_matte(req: MaskRequest):
    import json
    from app.services.segmentation import existing_masks, mask_duration
    clip = next((c for c in req.plan.clips if c.id == req.clip_id), None)
    if not clip:
        raise HTTPException(404, 'Video clip not found.')
    try:
        directory = existing_masks(clip, req.plan.aspect_ratio, req.plan.fit_mode, mask_duration(req.plan, clip))
        return json.loads((directory/'ready.json').read_text())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None

@router.get('/cinematic/masks/{key}/{frame}.png')
def mask_frame(key: str, frame: int, alpha: bool = False):
    import re
    if not re.fullmatch('[a-f0-9]{64}', key) or not 0 <= frame < 3600:
        raise HTTPException(404, 'Mask frame not found.')
    directory = CACHE_DIR / f'matte_{key}'
    path = directory / f'{frame:05d}.png'
    if not (directory/'ready.json').exists() or not path.is_file():
        raise HTTPException(404, 'Mask frame not ready.')
    if alpha:
        from PIL import Image
        alpha_path = directory / f'{frame:05d}_alpha.png'
        # Publish only a complete PNG, including when browser requests overlap.
        with _alpha_lock:
            if not alpha_path.exists():
                import tempfile
                from pathlib import Path
                with tempfile.NamedTemporaryFile(dir=directory, suffix='.part', delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                try:
                    with Image.open(path) as mask:
                        image = Image.new('RGBA', mask.size)
                        image.putalpha(mask.convert('L'))
                        image.save(temporary_path, format='PNG')
                    temporary_path.replace(alpha_path)
                finally:
                    temporary_path.unlink(missing_ok=True)
        path = alpha_path
    return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'private, max-age=86400'})

@router.get('/cinematic/title.png')
def cinematic_title(text: str = '', color: str = '#F2E9D8', ratio: Literal['9:16','16:9','1:1'] = '9:16', config: str | None = None, frame: int | None = None):
    from app.services.cinematic import title_image
    if len(text) > 120:
        raise HTTPException(400, 'Keep cinematic titles under 120 characters.')
    width, height = {'9:16': (1080,1920), '16:9': (1920,1080), '1:1': (1080,1080)}[ratio]
    try:
        from app.schemas.editing_plan import CinematicText
        title = CinematicText.model_validate_json(config) if config else None
        if frame is not None and not 0 <= frame <= 3600:
            raise ValueError('Invalid title frame.')
        return FileResponse(title_image(text,color,width,height,title,frame), media_type='image/png')
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

@router.post('/cinematic/captions')
def caption_previews(plan: EditingPlan):
    from app.services.caption_frames import caption_events
    width,height={'9:16':(1080,1920),'16:9':(1920,1080),'1:1':(1080,1080)}[plan.aspect_ratio]
    try:
        return [{k:v for k,v in event.items() if k!='path'} for event in caption_events(plan.subtitles,width,height)]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

@router.post('/cinematic/titles')
def title_previews(plan: EditingPlan):
    from app.services.cinematic import title_image
    width, height = {'9:16':(1080,1920),'16:9':(1920,1080),'1:1':(1080,1080)}[plan.aspect_ratio]
    return [{'id': title.id, 'frames': [f'/api/cinematic/titles/{title_image(title.text,title.color,width,height,title,frame).stem[5:]}.png'
             for frame in range(max(1, round(title.duration*30)))]} for title in plan.cinematic_texts]

@router.get('/cinematic/titles/{key}.png')
def title_frame(key: str):
    import re
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise HTTPException(404, 'Title frame not found.')
    path = CACHE_DIR / f'type_{key}.png'
    if not path.is_file():
        raise HTTPException(404, 'Title frame not ready.')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control':'private, max-age=86400'})

@router.get('/cinematic/captions/{key}.png')
def caption_image(key: str):
    import re
    if not re.fullmatch('[a-f0-9]{64}',key):
        raise HTTPException(404,'Caption image not found.')
    path=CACHE_DIR/f'caption_{key}.png'
    if not path.exists():raise HTTPException(404,'Caption image not found.')
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'private, max-age=86400'})
