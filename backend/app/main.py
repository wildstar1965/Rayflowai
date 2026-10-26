from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import CORS_ORIGINS, UPLOAD_DIR, ENVIRONMENT, MAX_REQUEST_MB
from app.core.request_limits import RequestSizeLimit
from app.api.health_routes import router as health_router
from app.api.routes import router
from app.api.creative_routes import router as creative_router
from app.api.caption_routes import router as caption_router
from app.api.settings_routes import router as settings_router
from app.api.analytics_routes import router as analytics_router
from app.services.job_history import recover_interrupted
from app.api.editor_routes import router as editor_router
from app.api.editor_live_routes import router as editor_live_router
from app.editor.accounts import router as accounts_router
from app.editor.teams import router as teams_router
from app.editor.collaboration import router as collaboration_router
from app.editor.middleware import WorkspaceMiddleware


@asynccontextmanager
async def lifespan(application):
    recover_interrupted()
    yield

app = FastAPI(
    lifespan=lifespan,
    title="RayFlow AI — Cinematic Reel Studio",
    description="Voice-driven cinematic video editing studio dedicated to Satyajit Ray",
    version="1.0.0",
    docs_url=None if ENVIRONMENT == 'production' else '/docs',
    redoc_url=None if ENVIRONMENT == 'production' else '/redoc',
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Pydantic includes rejected input in its default response, including key
    # submission bodies. Return only field locations and validation messages.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(error['loc']), 'msg': error['msg'], 'type': error['type']}
        for error in exc.errors()
    ]})

# CORS middleware
app.add_middleware(
    RequestSizeLimit, limit=MAX_REQUEST_MB * 1024**2,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploaded files share the request's authenticated workspace, including range requests.
@app.get('/api/uploads/{filename}')
def private_upload(filename: str):
    from app.editor.context import owner
    from app.editor.store import store, safe_relative
    safe_relative(filename)
    path = store.get_blob(owner(), 'uploads/' + filename)
    return FileResponse(path)
# Exports are served through the completed-job route, never a directory mount.

# Include API endpoints
app.include_router(router)
app.include_router(creative_router)
app.include_router(caption_router)
app.include_router(settings_router)
app.include_router(analytics_router)
app.include_router(health_router)
app.include_router(editor_router)
app.include_router(editor_live_router)
app.include_router(accounts_router)
app.include_router(teams_router)
app.include_router(collaboration_router)
app.add_middleware(WorkspaceMiddleware)

@app.get("/")
def root():
    return {
        "app": "RayFlow AI",
        "description": "Speak your vision. Shape the edit. Render the reel.",
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
