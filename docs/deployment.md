# Local development and production deployment

Rayflow is React 19 + Vite and one FastAPI process with local FFmpeg, SQLite job
history and bounded background threads. The Prisma schema is not connected to the
runtime. Projects remain in browser localStorage; the backend stores shared media
and job history. This deployment supports one authenticated, trusted workspace.
It is not a multi-tenant service with per-user storage isolation.

## Local development (PowerShell, repository root)

The existing environment was verified on Python 3.10 and Node 24. Keep an existing
working virtual environment; the creation command below is for a fresh setup with
Python 3.11 installed (also used by the container).

```powershell
py -3.11 -m venv backend/venv
backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt -c backend/constraints.txt
backend/venv/Scripts/python.exe -m pip install -r tests/requirements.txt
# Only copy templates when the destination does not exist; preserve existing keys.
if (!(Test-Path backend/.env)) { Copy-Item .env.example backend/.env }
if (!(Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
cd frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

In a second terminal at the repository root:

```powershell
backend/venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Use `http://127.0.0.1:5173`. `npm.cmd` avoids PowerShell's restriction on npm.ps1.
Backend process environment wins over `backend/.env`, which wins over legacy root
`.env`; locally saved provider values override those defaults. Existing credentials
are preserved. In production, set `RAYFLOW_ENV=production` in the process environment
before starting Python: neither dotenv files nor local provider files are read.

No API key is needed for editing or FFmpeg export. Speech needs a cached model:

```powershell
backend/venv/Scripts/python.exe backend/setup_local_assets.py --whisper medium
```

FFmpeg is included by imageio-ffmpeg locally. Install FFprobe on PATH or set
`FFPROBE_PATH` to its executable. `/api/health` is a cheap liveness check;
`/api/ready` checks required storage, SQLite, FFmpeg and FFprobe. Optional Ollama,
speech and paid API availability never block liveness. See [Ollama setup](ollama.md).

## Configuration

| Variable | Purpose |
| --- | --- |
| RAYFLOW_ENV | development (default), test or production |
| RAYFLOW_STORAGE_DIR | Uploads, exports, cache and SQLite; mandatory persistent mount in production |
| VITE_API_BASE_URL | Public frontend API URL, default /api; build-time only |
| RAYFLOW_API_PROXY_TARGET | Vite dev proxy, default http://127.0.0.1:8000 |
| CORS_ORIGINS | Comma-separated browser origins; production adds no localhost defaults |
| AI_PROVIDER | auto, local, ollama or openrouter |
| OPENROUTER_API_KEY / OPENROUTER_MODEL | Optional backend-only AI Director credentials/model |
| PIXABAY_API_KEY | Optional backend-only media-search key |
| OLLAMA_HOST / OLLAMA_MODEL | Reachable backend-to-model URL and installed model |
| OLLAMA_ALLOWED_HOSTS | Optional operator-approved extra model hosts |
| OLLAMA_GENERATION_TIMEOUT | Inference read limit, 1–600 seconds; default 180 |
| MAX_UPLOAD_MB / MAX_REQUEST_MB | Per-file limit (500) and total request body limit (1024) |
| RENDER_CONCURRENCY / RENDER_QUEUE_LIMIT | Simultaneous FFmpeg renders (1) / active plus queued renders (4) |
| RENDER_TIMEOUT_SECONDS | Worker render deadline, excluding queue wait (1800) |
| WHISPER_MODEL / WHISPER_DEVICE / WHISPER_COMPUTE_TYPE | Speech model and inference settings |
| HF_HOME | Persistent Hugging Face speech-model cache |
| PERSON_SEGMENTATION_MODEL | Optional local ONNX matting file; provision separately |

Keep provider secrets out of `VITE_*`, frontend files and logs. Production credentials
are environment variables managed by the operator. The process runs as an unprivileged
user in the supplied backend image. Configure storage permissions for UID 10001.
If you raise `MAX_REQUEST_MB`, update Caddy's `request_body max_size` accordingly.

## Container deployment on a Linux VM

Use a VM/container host with enough CPU/RAM/disk for the chosen models and long-running
FFmpeg processes. Short-lived serverless functions or static-only hosts cannot run the
backend. Install Docker Engine and Compose. Point a real DNS name to the host and allow
ports 80/443. The supplied Caddy service obtains TLS certificates and requires HTTP
Basic authentication for all pages, APIs, uploads and downloads.

1. Copy `deploy/backend.env.example` to `deploy/backend.env` and
   `deploy/compose.env.example` to `deploy/compose.env`. These private files are ignored
   by Git and excluded from container builds.
2. Set the hostname and username. Generate a password hash interactively:
   `docker run --rm -it caddy:2-alpine caddy hash-password`.
   Put the hash in single quotes in `RAYFLOW_PASSWORD_HASH`; do not commit it.
3. Choose `AI_PROVIDER=local`, configured OpenRouter, or a reachable private Ollama
   server. The sample loopback Ollama URL is unavailable inside the backend container
   unless Ollama runs in that same container; replace it for remote Ollama use.
4. Validate and build:

```sh
docker compose --env-file deploy/compose.env config --quiet
docker compose --env-file deploy/compose.env build
docker compose --env-file deploy/compose.env up -d
docker compose --env-file deploy/compose.env ps
```

The backend publishes no host port; Caddy is its only ingress. Do not publish port
8000 or 11434 directly. Single-workspace authentication happens at Caddy, not FastAPI.
For an existing platform ingress, require authentication on **every** backend/media
route, TLS and request limits. Enable CORS only for the exact frontend origin.
For cross-origin authenticated deployment, adapt credential handling to that gateway;
the supplied configuration deliberately uses a same-origin `/api` URL.

Cache speech models explicitly (download needs network access and disk space):

```sh
docker compose --env-file deploy/compose.env exec backend python setup_local_assets.py --whisper medium
docker compose --env-file deploy/compose.env exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/ready').read().decode())"
```

For a standalone frontend build: `cd frontend && npm ci && npm run build`. Set public
API URL variables before that build; serve `frontend/dist`, not the Vite dev server.
Backend dependencies are constrained to versions inspected locally; Linux image
resolution/build still requires verification on the host. No dependencies were upgraded.

## Persistence and operations

Named volumes retain uploads, generated videos, SQLite and model downloads. Back up
`rayflow_data` with the backend stopped (or use SQLite's backup API for the database)
and back up users' project interchange files separately. Browser localStorage does
not follow users to another browser or origin. Never delete volumes during upgrades.

Run exactly **one Uvicorn worker and one backend replica**. Threads and active job
registries are process-local. On restart, unfinished jobs become interrupted in
analytics; users must rerun them. Completed MP4 downloads survive restart. Renders
have bounded admission/concurrency, cancellation and a configured deadline. Creative
jobs are bounded and transcription inference is serialized. Progress comes from
actual processing stages; queue time is excluded from average render duration.

Render intermediates are cleaned by the existing worker; failures/restarts may leave
job directories. Inspect only `exports/job_*` after stopping the backend before
removing abandoned intermediates. Uploads/final exports are intentionally retained:
there is no automatic deletion that might break saved projects. Monitor disk use.
Distributed workers, durable queue replay and object storage require an additional
architecture change before horizontal scaling or multiple isolated users.

## Verification limits

Run the commands/results recorded in [phase 5–8 verification](phases-5-8-report.md).
Docker build, Caddy TLS/auth, Linux font rendering, mounted-volume ownership, firewall
rules and hosted model reachability require the actual container/hosting environment.
They must pass there before publishing the service. No deployment has been performed.
