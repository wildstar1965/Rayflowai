FROM node:24-bookworm-slim AS editor-runtime
WORKDIR /runtime
COPY backend/editor-runtime/package*.json ./
RUN npm ci --omit=dev
COPY backend/editor-runtime/ ./

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt backend/constraints.txt ./
# Resilient install for slower/CI networks: longer per-read timeout and retries.
RUN python -m pip install --timeout 180 --retries 10 -r requirements.txt -c constraints.txt
COPY backend/app ./app
COPY backend/assets ./assets
COPY backend/setup_local_assets.py ./
COPY --from=editor-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=editor-runtime /runtime ./editor-runtime
RUN useradd --create-home --uid 10001 rayflow && mkdir -p /data /models \
    && chown rayflow:rayflow /data /models
USER rayflow
ENV RAYFLOW_ENV=production RAYFLOW_STORAGE_DIR=/data HF_HOME=/models/huggingface \
    FFPROBE_PATH=/usr/bin/ffprobe IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/ready', timeout=12)"
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-proxy-headers --timeout-graceful-shutdown 30"]
