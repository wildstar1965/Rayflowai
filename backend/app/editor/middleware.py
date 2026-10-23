"""Apply the same ownership boundary to new editor and original Rayflow routes."""
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import HTTPException
from .context import workspace_id, account
from .security import COOKIE, resolve_session, require_origin
from .store import store, Conflict, StorageUnavailable


class WorkspaceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if not path.startswith('/api/') or path in ('/api/health', '/api/ready') or request.method == 'OPTIONS':
            return await call_next(request)
        token = None
        account_token = None
        try:
            record = resolve_session(request.cookies.get(COOKIE))
            if record:
                token = workspace_id.set(record['workspace_id'])
                account_token = account.set(record.get('account'))
                from app.core.config import UPLOAD_DIR, EXPORT_DIR, CACHE_DIR
                for directory in (UPLOAD_DIR, EXPORT_DIR, CACHE_DIR):
                    directory.mkdir(parents=True, exist_ok=True)
            elif path != '/api/session' and (path.startswith('/api/editor/') or os.getenv('RAYFLOW_ENV') == 'production'):
                # Preserve the existing public, masked operator-status response.
                # All user-specific configuration still requires a session.
                if path != '/api/settings' or request.method != 'GET':
                    return JSONResponse({'detail': 'Start or restore your workspace session.'}, status_code=403 if path == '/api/settings' else 401)
            if request.method not in ('GET', 'HEAD'):
                require_origin(request)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            if '/files/' in path or path.startswith('/api/editor/assets/file/') or path.startswith('/api/uploads/'):
                response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'"
            return response
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
        except Conflict as exc:
            return JSONResponse({'detail': str(exc)}, status_code=409)
        except StorageUnavailable as exc:
            return JSONResponse({'detail': str(exc)}, status_code=503)
        except PermissionError:
            return JSONResponse({'detail': 'A workspace session is required.'}, status_code=401)
        except FileNotFoundError:
            return JSONResponse({'detail': 'The requested file was not found in this workspace.'}, status_code=404)
        except ValueError as exc:
            return JSONResponse({'detail': str(exc)}, status_code=422)
        finally:
            if account_token is not None:
                account.reset(account_token)
            if token is not None:
                workspace_id.reset(token)
