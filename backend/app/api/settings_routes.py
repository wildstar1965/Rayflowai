import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from app.core.config import CORS_ORIGINS
from app.services.provider_settings import public_settings, save_settings, test_provider

router = APIRouter(prefix='/api/settings', tags=['configuration'])


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    values: dict[str, str]


def require_local_settings(request):
    from app.editor.context import workspace_id
    if workspace_id.get():
        from app.editor.security import require_origin
        require_origin(request)
        return
    if os.getenv('RAYFLOW_ENV', 'development') == 'production':
        raise HTTPException(403, 'Production credentials are managed by the server operator.')
    if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise HTTPException(403, 'Provider changes are available only on the local backend.')
    origin = request.headers.get('origin')
    if origin and origin not in CORS_ORIGINS and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'This origin cannot change provider settings.')


@router.get('')
def get_settings():
    try:
        return public_settings()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None


@router.put('')
def update_settings(patch: SettingsPatch, request: Request):
    require_local_settings(request)
    try:
        save_settings(patch.values)
        return public_settings()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except OSError:
        raise HTTPException(503, 'Cannot save private configuration. Check backend storage permissions.') from None


@router.post('/test/{provider}')
def connection_test(provider: str):
    try:
        return test_provider(provider)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
