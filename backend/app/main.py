from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import CORS_ORIGINS, UPLOAD_DIR, EXPORT_DIR
from app.api.routes import router
from app.api.creative_routes import router as creative_router

app = FastAPI(
    title="RayFlow AI — Cinematic Reel Studio",
    description="Voice-driven cinematic video editing studio dedicated to Satyajit Ray",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static file directories for uploads and exports
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
# Exports are served through the completed-job route, never a directory mount.

# Include API endpoints
app.include_router(router)
app.include_router(creative_router)

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
