# RayFlow AI — Google Cloud Run Deployment

This guide deploys RayFlow AI to **Google Cloud Run** using Cloud Run Services
(frontend + backend) and a Cloud Run Job (rendering), with Cloud Storage for
media, Secret Manager for credentials, Artifact Registry for images, and Cloud
Build for CI/CD.

> Target platform is **Cloud Run only**. No Compute Engine, no GKE, no
> production Docker Compose. Compose remains for local development.

Pre-filled defaults for this project (override via env/substitutions):

| Setting | Value |
| --- | --- |
| Project ID | `ladysingham` |
| Project number | `434846178878` |
| Region | `asia-south1` (Mumbai) |
| Artifact Registry repo | `rayflow` |
| Backend service | `rayflow-backend` |
| Frontend service | `rayflow-frontend` |
| Render job | `rayflow-render` |
| GCS bucket | `rayflow-storage-ladysingham` |

## Architecture

```
Browser ──HTTPS──▶ rayflow-frontend (Cloud Run Service, nginx)
                      │  /api/* reverse-proxied
                      ▼
                   rayflow-backend (Cloud Run Service, FastAPI + FFmpeg)
                      │ export request → persist job + task, trigger Job
                      ▼
                   rayflow-render (Cloud Run Job, FFmpeg)
                      │ pulls source media + uploads MP4
                      ▼
                   Cloud Storage (ONE private bucket):
                     • records/  → projects, jobs, taste profiles (JSON)
                     • uploads/ projects/ exports/ → media (blobs)
                   Secret Manager (QLOO_API_KEY, vault secret, optional LLM keys)
```

The backend and render job **do not share a filesystem**. Cloud Storage is the
handoff and the system of record. Render status is persisted so it survives
instance restarts, and Cloud Run Job execution status is distinct from FFmpeg
progress. No Supabase or Cloud SQL is required.

## 0. Prerequisites

- `gcloud` CLI authenticated (Cloud Shell is already authenticated).
- A Qloo hackathon API key.

**No external database.** Persistence (projects, jobs, taste profiles) and media
both live in a single **private Google Cloud Storage bucket**. Records are stored
as JSON objects with atomic optimistic-concurrency writes; media/exports are
stored as blobs. No Supabase or Cloud SQL is required.

```bash
export PROJECT_ID=ladysingham
export REGION=asia-south1
export REPO=rayflow
export PROJECT_NUMBER=434846178878
gcloud config set project "$PROJECT_ID"
```

## 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com
```

## 2. Artifact Registry

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="RayFlow AI images"
```

## 3. Cloud Storage bucket (private)

```bash
gcloud storage buckets create gs://rayflow-storage-ladysingham \
  --location="$REGION" \
  --uniform-bucket-level-access \
  --public-access-prevention

# Optional: expire temporary thumbnails/exports after 30 days.
cat > /tmp/lifecycle.json <<'EOF'
{ "rule": [ { "action": {"type":"Delete"}, "condition": {"age": 30, "matchesPrefix": ["thumbnails/"]} } ] }
EOF
gcloud storage buckets update gs://rayflow-storage-ladysingham --lifecycle-file=/tmp/lifecycle.json
```

## 4. Secret Manager

Only two secrets are required (values never go in the repo or images):

```bash
printf '%s' 'YOUR_QLOO_KEY' | gcloud secrets create QLOO_API_KEY --data-file=-
# 32+ byte random string for encrypting per-workspace provider credentials:
python3 -c "import secrets;print(secrets.token_urlsafe(48))" | gcloud secrets create RAYFLOW_VAULT_SECRET --data-file=-

# Optional LLM key(s) — enables LLM taste interpretation / AI Director:
# printf '%s' 'YOUR_GEMINI_KEY' | gcloud secrets create GEMINI_API_KEY --data-file=-
```

## 5. IAM (least privilege)

The Cloud Run services run as the default compute service account unless you
create a dedicated one. Grant it only what it needs:

```bash
export RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Read the required secrets.
for S in QLOO_API_KEY RAYFLOW_VAULT_SECRET; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done

# Read/write media in the bucket.
gcloud storage buckets add-iam-policy-binding gs://rayflow-storage-ladysingham \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectAdmin"

# Allow the backend to trigger the render Job.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/run.developer"

# Let Cloud Build deploy Cloud Run + use the runtime SA.
export CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${CB_SA}" --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${CB_SA}" --role="roles/artifactregistry.writer"
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --member="serviceAccount:${CB_SA}" --role="roles/iam.serviceAccountUser"
```

## 6. Build & deploy (Cloud Build)

One command builds all three images (tagged with the commit SHA), pushes them,
and deploys both services + the job:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="$REGION",_REPO="$REPO",_GCS_BUCKET=rayflow-storage-ladysingham,SHORT_SHA="$(git rev-parse --short HEAD)"
```

The pipeline:
1. Builds `backend`, `render-worker`, `frontend` images.
2. Pushes them to Artifact Registry with the commit SHA tag (immutable).
3. Deploys `rayflow-backend` (private) with env + Secret Manager bindings.
4. Creates/updates the `rayflow-render` Cloud Run Job.
5. Deploys `rayflow-frontend` (public), wiring `BACKEND_URL` to the backend.

### Manual deploy (equivalent, if you prefer not to use Cloud Build)

```bash
# Backend
gcloud run deploy rayflow-backend \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/backend:$(git rev-parse --short HEAD)" \
  --region="$REGION" --no-allow-unauthenticated --port=8000 \
  --cpu=2 --memory=2Gi --concurrency=20 --timeout=900 --max-instances=4 \
  --set-env-vars=RAYFLOW_ENV=production,RAYFLOW_STORAGE_DIR=/tmp/rayflow,GCS_BUCKET=rayflow-storage-ladysingham,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},RENDER_CLOUD_RUN_JOB=rayflow-render \
  --set-secrets=QLOO_API_KEY=QLOO_API_KEY:latest,RAYFLOW_VAULT_SECRET=RAYFLOW_VAULT_SECRET:latest

# Render Job
gcloud run jobs create rayflow-render \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/render-worker:$(git rev-parse --short HEAD)" \
  --region="$REGION" --tasks=1 --max-retries=1 --task-timeout=2000 --cpu=2 --memory=4Gi \
  --set-env-vars=RAYFLOW_ENV=production,RAYFLOW_STORAGE_DIR=/tmp/rayflow,GCS_BUCKET=rayflow-storage-ladysingham,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION} \
  --set-secrets=QLOO_API_KEY=QLOO_API_KEY:latest,RAYFLOW_VAULT_SECRET=RAYFLOW_VAULT_SECRET:latest

# Frontend (wire to backend URL)
BACKEND_URL=$(gcloud run services describe rayflow-backend --region="$REGION" --format='value(status.url)')
gcloud run deploy rayflow-frontend \
  --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/frontend:$(git rev-parse --short HEAD)" \
  --region="$REGION" --allow-unauthenticated --port=8080 --cpu=1 --memory=512Mi \
  --set-env-vars=BACKEND_URL="$BACKEND_URL"
```

## 7. Verify

```bash
# Frontend reachable
FRONTEND_URL=$(gcloud run services describe rayflow-frontend --region="$REGION" --format='value(status.url)')
curl -sfI "$FRONTEND_URL" && echo "frontend OK"

# Backend readiness through the frontend proxy
curl -sf "$FRONTEND_URL/api/ready" | python -m json.tool

# Watch logs
gcloud run services logs read rayflow-backend --region="$REGION" --limit=50
gcloud run jobs executions list --job=rayflow-render --region="$REGION"
```

Then in the browser: open the frontend URL → **Discover Your Taste** → enter
preferences → Studio → upload media → **Create a Reel Based on My Taste** →
Export MP4.

## Notes & limits

- **Rendering model**: the backend validates the export request, persists a job
  + task, then triggers the render Job. The Job pulls source media from GCS,
  runs the existing FFmpeg pipeline, uploads the MP4 to GCS, and updates job
  status. The frontend polls `/api/render/{job_id}` as before.
- **Cold starts**: `min-instances=0` saves cost but adds latency. Set
  `--min-instances=1` on the backend for a hackathon demo if desired.
- **Whisper captions**: local model weights are not bundled. Speech captions
  require provisioning the model (see the main README); manual captions work
  without it.
- **CPU-only rendering** on Cloud Run: long reels take longer. Tune the Job's
  `--cpu`/`--memory`/`--task-timeout` for your content.
- This document describes the deployment; **no deployment is performed by the
  repository itself.** Run the commands above on your GCP project.
