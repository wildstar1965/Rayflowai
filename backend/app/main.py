from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import CORS_ORIGINS, UPLOAD_DIR, EXPORT_DIR
from app.api.routes import router

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
app.mount("/api/exports", StaticFiles(directory=str(EXPORT_DIR)), name="exports")

# Include API endpoints
app.include_router(router)

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
