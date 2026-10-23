"""Caption documents follow Rayflow's client-owned project/undo model."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.schemas.captions import CaptionDocument, CaptionImportRequest
from app.services.caption_documents import export_document, import_engine_transcript
from app.services.speech_transcription import transcription_source, WHISPER_MODELS, source_fingerprint

router = APIRouter(prefix='/api/captions', tags=['captions'])


@router.get('/models')
def speech_models():
    from app.services.speech_models import model_catalog
    return model_catalog()


@router.post('/models/check')
def check_speech_models():
    from app.services.speech_models import start_model_check, model_catalog
    start_model_check()
    return model_catalog()


@router.get('/capabilities')
def capabilities():
    from faster_whisper.tokenizer import _LANGUAGE_CODES
    from PIL import features
    return {'provider': 'faster-whisper', 'local': True, 'models': WHISPER_MODELS,
            'languages': sorted(_LANGUAGE_CODES), 'formats': ['srt', 'vtt', 'ass', 'json'],
            'complex_script_shaping': features.check_feature('raqm'),
            'roman_scripts': ['Devanagari', 'Kannada'], 'translation': False, 'diarization': False}


@router.post('/validate', response_model=CaptionDocument)
def validate_document(document: CaptionDocument):
    return document


@router.post('/export/{fmt}')
def export_captions(document: CaptionDocument, fmt: Literal['srt', 'vtt', 'ass', 'json'],
                    aspect_ratio: Literal['9:16', '16:9', '1:1'] = '9:16'):
    width, height = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[aspect_ratio]
    media_type = {'srt': 'application/x-subrip', 'vtt': 'text/vtt', 'ass': 'text/plain', 'json': 'application/json'}[fmt]
    return Response(export_document(document, fmt, width, height).encode('utf-8'),
                    media_type=media_type, headers={'Content-Disposition': f'attachment; filename="rayflow-captions.{fmt}"'})


@router.post('/import')
def import_captions(request: CaptionImportRequest):
    try:
        path = transcription_source(request.media_filename)
        subtitles = import_engine_transcript(request.transcript, path.name, request.use_roman)
    except FileNotFoundError:
        raise HTTPException(404, 'Select the uploaded source for this transcript.') from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {'subtitles': [s.model_dump() for s in subtitles], 'source_filename': path.name,
            'source_fingerprint': source_fingerprint(path), 'language': request.transcript.language}
