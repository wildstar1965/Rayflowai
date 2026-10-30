# RayFlow AI — Security Overview

This document summarizes the security posture of RayFlow AI, with emphasis on
the Qloo integration and the Cloud Run deployment. It complements the existing
backend security model (workspace isolation, private storage, encrypted
provider credentials).

## Secrets & credentials

- **Qloo key is backend-only.** `QLOO_API_KEY` is read via
  `setting('QLOO_API_KEY')` and sent only in the `X-Api-Key` request header to
  `hackathon.api.qloo.com`. It is never exposed to the frontend, never placed in
  a `VITE_`-prefixed variable, and never written to the built bundle.
- **LLM keys are backend-only.** Provider keys (Gemini/OpenAI/Anthropic/
  OpenRouter/Agent Router) are stored encrypted per workspace or supplied via
  the backend environment; they are never returned to the browser.
- **No secrets in images or git.** Dockerfiles copy source only. `.gitignore`
  excludes `.env`, `.env.production`, `.env.*`, local storage dirs, and SQLite.
  `.env.production.example` contains variable **names** and placeholders only.
- **Secret Manager in production.** On Cloud Run, secrets are injected via
  `--set-secrets` from Google Secret Manager; the runtime service account has
  `roles/secretmanager.secretAccessor` on exactly those secrets (least
  privilege). `cloudbuild.yaml` contains no secret values.
- **No secret logging.** The Qloo client never logs the key or echoes upstream
  error bodies that might contain sensitive detail.

## Privacy

- **User media is never sent to Qloo.** Only declared cultural preference text
  (and the entity/tag IDs derived from it) are sent. Uploaded photos, videos,
  and audio never leave RayFlow's own storage for Qloo.
- Qloo responses are cached only in process memory, never persisted to a public
  location (consistent with Qloo's terms).
- Taste profiles are stored per workspace and scoped by the same ownership
  predicate as all other records.

## Input validation & safe operations

- **AI output is validated before use.** The Taste Intelligence strategy is
  validated against `TasteEditingStrategy` (Pydantic) with every field
  constrained to renderer-supported enums. The AI Director validates actions
  against a fixed action registry. The agent cannot emit an arbitrary or
  unsupported operation, and no LLM text is ever executed as a shell command.
- **Approval preserved.** Taste-aware Director edits and taste "apply" return a
  proposed plan for user review; nothing is applied without explicit approval.
- **Request validation.** All taste routes use Pydantic models with
  `extra='forbid'`, bounded list sizes, and length limits.
- **Path traversal prevented.** Blob access goes through `safe_relative()`,
  which rejects absolute paths, `..`, drive letters, and backslashes. GCS object
  names are derived from the validated relative path and the workspace ID.
- **Upload limits.** `MAX_UPLOAD_MB` / `MAX_REQUEST_MB` and a request-size
  middleware bound uploads; media types are validated and probed.

## Transport & network

- **HTTPS only for Qloo.** The client rejects a non-HTTPS base URL.
- **No SSRF via Qloo config.** Only the documented hackathon host (or an
  explicit operator override) is used; the key is header-only.
- **Retries are bounded** (max 3) with capped backoff, honoring `Retry-After`,
  so a misbehaving upstream cannot cause unbounded load.
- **Render Job trigger** uses the Cloud Run Admin API with the service's own
  metadata-server token; no long-lived keys are embedded.

## Authorization & isolation

- Every taste route requires an authenticated workspace session and operates on
  `owner()`-scoped records, matching the rest of the editor.
- The AI Director's taste context is **populated server-side** from the saved
  profile; any client-supplied `taste_profile` is ignored and overwritten, so it
  cannot be spoofed.
- Per-workspace rate limiting guards Qloo-backed analysis endpoints.

## Containers & runtime

- **Non-root containers.** The backend and render-worker images run as an
  unprivileged `rayflow` user (uid 10001). The frontend serves static files via
  nginx on an unprivileged high port.
- **Health checks** on the backend (`/api/ready`), restart policies in Compose,
  and graceful shutdown (`--timeout-graceful-shutdown`) for in-flight work.
- **Private storage by default.** The GCS bucket uses uniform access and public
  access prevention; downloads are served by the backend or via short-lived
  signed URLs.
- **CORS** is empty by default in production (same-origin via the frontend
  proxy); cross-origin use must be explicitly allow-listed.
- **Security headers** are set by both the backend and the nginx frontend
  (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`).

## Responsible disclosure

If you find a vulnerability, do not open a public issue with exploit details.
Contact the maintainers privately with reproduction steps so it can be addressed
before disclosure.
