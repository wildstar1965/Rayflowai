# Rayflow on Vercel, Render, and Supabase

The complete application is built from Rayflow. The editor is a lazy-loaded React
section at `#/editor`; FastAPI owns sessions, projects, providers, and processing.
The internal Node worker runs SDK/media operations and has no public HTTP server.

**Deployment status:** configuration prepared; no Supabase project, Render service,
or Vercel deployment has been created or smoke-tested. See
[the integration report](ai-editor-integration.md) for actual local evidence.

## Supabase

1. Create a Supabase project and run `supabase/migrations/202610230001_rayflow_editor.sql`.
2. Keep the `rayflow-private` bucket private. Do not grant anonymous access to the
   records table or bucket. The server creates scoped upload/download tickets.
3. Obtain the project URL and backend service-role key for Render. They are not
   provider keys and the service-role key must never be placed in frontend variables.
4. Optional accounts use Supabase email OTP. Enable email authentication and configure
   the email template to display `{{ .Token }}`. The Connections form accepts the code;
   a magic-link-only email template does not complete that flow. Configure an SMTP
   sender and test delivery before enabling accounts for judges.

## Render

Create the Docker web service using the repository's `render.yaml`. Configure the
values from `deploy/editor.env.example`. Keep `RAYFLOW_VAULT_SECRET` stable across
deployments: changing it without migrating encrypted records makes saved keys unreadable.
Set the exact Vercel production origin in both origin variables. Render supplies
`RENDER_EXTERNAL_URL` for direct WebSocket connections.

The backend's local storage is temporary scratch space. Projects, credentials,
uploaded assets, generated outputs, and job records use Supabase. Interrupted work
is reported as interrupted; a generation is not automatically resubmitted and charged
again. Free compute may sleep and has limited memory; test real media on the chosen
instance before the judging session. Local model services require separately provisioned
servers reachable by Render.

Run one Uvicorn process/replica with the supplied configuration. Queue admission and
active process cancellation use in-process coordination. Scaling to multiple backend
replicas requires distributed scheduling first. `EDITOR_JOB_CONCURRENCY` limits active
editor jobs, `EDITOR_QUEUE_LIMIT` bounds each workspace, and
`EDITOR_GLOBAL_QUEUE_LIMIT` bounds total admitted editor jobs. Studio rendering has its
own `RENDER_CONCURRENCY` limit. Set all values to fit the selected instance.

## Vercel

Import this repository with **Root Directory = frontend**, framework Vite, output
`dist`. Replace the backend hostname in `frontend/vercel.json` with the actual Render
service URL if it differs from `rayflow-ai-api.onrender.com`. Leave the frontend API
base at `/api` so the guest cookie stays on the application origin.

Do not add provider keys, vault secrets, or Supabase service-role keys to Vercel's
client build variables. Large editor asset uploads use signed Supabase URLs; provider
operations return short job responses and are polled. Live voice uses a one-use ticket
to connect directly to Render over WSS, without placing credentials in the URL.
Studio image, audio, and video uploads also use the direct Storage path in hosted mode.
The browser then asks FastAPI to validate and adapt the owned asset for Studio.

Use Node 24 for the current Vite/tooling versions. Both dependency installs and lockfiles
are now complete; the normal TypeScript/production build and nine browser workflows pass
locally against the built files. Vercel and the worker Docker stage use npm ci. Earlier
diagnostic previews using upstream packages are not the basis for this build result.

## Local development

```powershell
cd frontend
npm install
npm run dev
# Separate terminal, repository root:
backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd backend/editor-runtime
npm install
# Repository root:
backend/venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Without Supabase, development uses private SQLite records and workspace folders.
A local encryption key is generated in ignored private storage. Production requires
Supabase and an explicitly configured vault secret.

Judges can skip provider setup and use import/edit/export workflows. Adding a key
enables its provider; remove it in Connections when finished. A guest workspace is
restored by the same browser's HttpOnly cookie for seven days. Losing the cookie loses
guest access; download project archives for portability. API tests do not run paid
generation unless the user explicitly starts the corresponding action.

## Optional integrations

- **Drive and Dropbox:** register OAuth applications, configure their backend-only
  client IDs/secrets, and allow the exact callback
  `https://YOUR-VERCEL-HOST/api/editor/cloud/callback`. Set `RAYFLOW_FRONTEND_URL` to that
  same origin. Authorization uses per-session state and PKCE; refresh tokens are
  encrypted in backend storage. Users connect and disconnect in Connections. Actual
  consent, refresh, and two-way cloud file synchronization remain live-test requirements.
- **Teams:** sign in by verified email code, create a team, and share a project copy.
  Invitations are single-use and expire after one day. Viewer roles cannot save changes
  to shared projects. Team sharing copies authorized media; personal credentials and
  generation jobs remain private. The collaboration relay runs inside FastAPI.
- **NotebookLM:** set `EDITOR_NOTEBOOKLM_URL` to an operator-provisioned HTTP MCP service.
  A judge saves its access token in Connections. Server startup/installation is an
  operator responsibility. The adapter has mocked protocol checks, not a live NotebookLM
  service test.
- **Local AI:** set only the model services reachable from Render. The backend maps the
  imported default localhost addresses to these operator targets; judges cannot select
  arbitrary internal network targets. Ollama, LM Studio, OpenAI-compatible, ComfyUI, and
  Draw Things remain configuration-dependent.
- **ComfyUI:** use a dedicated service with the expected models installed. Hosted requests
  namespace input/output files per workspace and authorize prompt history/output access.
  Global queue, interrupt, install, and history controls are unavailable to guests. The
  built-in node allowlist can be extended with `EDITOR_COMFYUI_EXTRA_NODES` only after
  auditing custom nodes. Custom node filesystem/network behavior is outside the relay's
  isolation; do not add unrestricted execution nodes to a shared judging server.
- **GPU processors:** the base Docker image does not provision GPUs or model weights.
  Depth Anything V2 needs `EDITOR_SURFACE_MAP_REPO`, its `run.py`, checkpoints, and Python
  dependencies. CorridorKey needs `EDITOR_CORRIDOR_KEY_REPO`, `corridorkey_cli.py`, `uv`,
  dependencies, and weights. Rebuild/provision an appropriate worker environment before
  setting those paths. CPU depth-gradient normal maps and the included audio processors
  have local execution tests. A filesystem readiness check alone does not prove a GPU
  processor can run.

## Generation results and recovery

Provider HTTP calls and SDK operations become owned jobs with durable submission keys.
Provider receipts are recorded where the adapter can identify an operation. Dashboard's
**Check existing provider result** polls that receipt without submitting another paid
generation. It is a manual recovery action, not automatic resumption of every production
step. An ambiguous interrupted submission is not automatically retried.

Generated media is copied into private storage before the job reports successful output
persistence. If a provider uses an additional CDN, configure exact trusted hostnames in
`EDITOR_<PROVIDER>_OUTPUT_HOSTS` (for example `EDITOR_RUNWAY_OUTPUT_HOSTS`) and retry saving
the existing result. Redirects are validated and credentials are not forwarded to CDN
hosts. `EDITOR_OUTPUT_MAX_MB` bounds each downloaded output. Provider-specific response
shapes and CDN changes still need live testing; a transport contract test does not prove
every generation model or asset format works.

Interrupted local processing is reported as interrupted/retryable. Required input files
are reconstructed from Storage, and completed outputs do not depend on Render scratch
space. Back up the Supabase database, private bucket, and vault secret together; rotating
the vault secret requires an explicit credential migration.

## Publication checks

Create two independent browser sessions and verify private projects, files, keys, jobs,
uploads, exports, restart recovery, and live voice. Run the integration test suite
against the deployment. Local tests alone do not prove the cloud configuration works.
The service accounts were not yet created when implementation began; no public URL
or successful cloud deployment is implied by these configuration files.

Check direct signed image/audio/video uploads; playback and range requests; private
download expiry; two-guest denial of projects, credentials, jobs, and files; real MP4
output; backend restart and scratch-file reconstruction; provider receipt recovery;
WSS ticket consumption and voice; optional OTP/OAuth; and concurrent shared-project
editing. Local H.264, 10-bit HEVC and 10-bit ProRes exports pass real decoding checks.
Volume easing, trimmed audio at changed speed, custom 1D/3D LUTs, private Quick WebM
and export cancellation/retry have local checks. Jobs remove their temporary processing
directory after output persistence. Quick export captures video only; HQ still rejects
text overlays, transitions, chroma key, non-normal blends and opacity keyframes.
Deployment codecs, HDR/color metadata, native VFX host imports, and every configured
provider model still need output checks. Keep upstream GPL notices in source and
distribution; see `frontend/src/features/ai-editor/NOTICE` and bundled `LICENSE`.

The frontend npm audit reports seven development-only Tailwind dependency findings
(five high, two moderate). npm recommends a major Tailwind upgrade. The affected
compiler/watcher packages are not application runtime dependencies; the migration has
not been performed as part of the editor integration. Backend worker npm audit reports
zero findings. Recheck advisories when deploying. Build output also contains warnings
about large editor chunks and mixed static/dynamic imports.
