# Rayflow phases 5–8 implementation and verification

Date: 23 October 2026. Scope: complete the remaining phases on top of the existing
phase 1–4 work. Existing editor, landing design, caption/reference adapters, project
data, credentials and unrelated uncommitted changes were preserved. No deployment
or commit was performed.

## Implemented

- **Phase 5:** Extended the existing SQLite lifecycle history and native dashboard.
  Added failed/cancelled/interrupted counts and seven days of UTC completion activity,
  consistent database snapshots, focus/cross-tab refresh, last-updated time and
  robust saved-project parsing. Existing exports, caption jobs, active jobs, success
  rate and average render time remain measured from actual worker events. Formulas
  and exclusions are in [analytics.md](analytics.md).
- **Phase 6:** Replaced the disconnected Ollama transport with the shared provider
  settings reader. Added explicit model validation, real prompt diagnostics,
  configurable generation timeout, bounded discovery retry, useful errors, permitted
  remote hosts, redirect rejection and prompt-response validation. The editor honors
  the saved provider preference, and B-roll uses the saved model selection.
- **Phase 7:** Added persistent-storage configuration, production dotenv isolation,
  numeric/origin validation, readiness checks, upload/request limits, bounded render
  concurrency and timeout, cancellation admission fixes, and deployment templates.
  The provided Caddy configuration authenticates all routes and terminates HTTPS;
  the backend is not published directly. This is a single trusted workspace deployment.
- **Phase 8:** Added analytics, Ollama, deployment and browser regression coverage,
  a browser runner that uses isolated services/storage, and `npm test`. Increased the
  existing browser fixture's bounded startup allowance after a real startup timeout.

The reference `src/portal/pages/Analytics.tsx` only displays usage rows from its
data service; no reusable render KPI math exists there. The local model discovery
behavior is compatible with the reference's `localLlmService.ts`, but Rayflow needs
Python backend transport instead of its Electron/Gemini adapter. Existing reference
caption grouping and OTIO export were preserved and regression-tested, not recopied.

## Actual Ollama results

- Backend discovery: HTTP 200; installed model `qwen3:8b`; ready status true.
- Backend prompt test: HTTP 200; actual model response `Ready.` in 21.67 seconds.
- Actual structured model inference: parsed and applied square aspect ratio and noir
  style to an in-memory test plan. No saved user project was changed.
- Root causes: the client ignored saved host/model configuration, silently replaced
  missing models, only allowed local HTTP hosts, hid failures behind fallback, and
  used a 12-second inference timeout. The UI's prompt-test route was absent.
  The measured 21.67-second reply exceeded that old deadline.
- Existing non-streaming behavior is preserved (`stream: false`). Streaming was not
  previously implemented and is not claimed here.
- Production model access requires an address reachable from the backend environment;
  cloud/container loopback cannot reach the user's desktop Ollama. See [ollama.md](ollama.md).

## Important files

| Files | Purpose |
| --- | --- |
| backend/app/services/job_history.py | Persistent lifecycle metrics and daily activity |
| frontend/src/pages/DashboardPage.tsx | Measured KPI display, refresh/error states, saved project summary |
| backend/app/services/ollama_client.py | Discovery, validated generation, model selection and safe diagnostics |
| backend/app/services/provider_settings.py | Live settings, blank-model reset and production credential isolation |
| backend/app/api/routes.py | Prompt-test route, Ollama errors, local provider preference, upload/queue limits |
| frontend/src/pages/SettingsPage.tsx | Reconnect, installed models and actual prompt-response display |
| frontend/src/pages/StudioPage.tsx | Preferred provider routing and accurate Ollama readiness display |
| frontend/src/services/api.ts | Ollama request deadline and readiness type |
| backend/app/services/broll.py | Shared selected model for concept extraction |
| backend/app/core/config.py | Environment, storage, origin and numeric validation |
| backend/app/core/request_limits.py | Declared and streamed request-body limits |
| backend/app/api/health_routes.py; backend/app/main.py | Readiness and middleware/startup integration |
| backend/app/services/video_renderer.py; creative_jobs.py | Bounded workers, deadline, cancellation admission and startup failure handling |
| backend/Dockerfile; frontend/Dockerfile; compose.yaml; deploy/Caddyfile | Single-workspace deployment topology |
| .dockerignore; .gitignore; environment examples | Exclude secrets/media from builds and separate configuration |
| backend/constraints.txt | Locally inspected dependency versions; Linux resolution still needs validation |
| frontend/vite.config.ts; frontend/package.json | Load dev proxy environment and expose regression test command |
| tests/test_job_history.py; test_ollama_connection.py; test_deployment.py | Formula, transport, persistence, admission and production tests |
| tests/test_integration_browser.py; run_browser_checks.py; test_studio_browser.py | UI regression checks and isolated/bounded test startup |

## Verification record

All commands ran from the repository root unless a frontend working directory is
specified. Test temporary directories and media were isolated under `test_artifacts`.
The full backend run used a unique `RAYFLOW_STORAGE_DIR` to avoid adding test jobs to
the user's history.

Final browser coverage across scoped runs: **26 passed, 2 skipped**. The skips are
only the two opt-in personal-reference comparisons whose source media was not copied
into isolated test storage. No product regression remains failing in the executed
regression set. Earlier failed attempts and their corrections are recorded below.

| Check / command | Actual result |
| --- | --- |
| `python -m pytest tests/test_job_history.py -q` with workspace `--basetemp` | 6 passed at phase 5 |
| Ollama/provider/offline suite | 24 passed at phase 6 |
| Deployment/history/Ollama/provider suite | 33 passed at phase 7 |
| Full `test_*.py` suite excluding `test_*browser.py` | 181 passed in 461.92 seconds; 2 Pydantic serialization warnings |
| Expanded production startup/download checks | 8 passed after adding lifecycle and persisted-download checks |
| `python tests/run_browser_checks.py` | 8 passed against production preview; final rerun also passed all 8 (260.24 seconds under load) |
| Final targeted deployment/history/Ollama/provider suite | 36 passed after final cancellation and configuration corrections |
| Corrected editor/numeric browser checks | 14 passed across targeted runs; 1 opt-in reference-source comparison skipped |
| Export-duration/download/playback browser checks | 2 passed in 101.28 seconds; 1 opt-in quality-source comparison skipped |
| Real speech-caption browser checks | 2 passed in 127.15 seconds with the cached Medium model: transcription, word timings, manual edits/regeneration, import/export, reload, native-script preview versus MP4, and retained source audio |
| `npm.cmd run build` in frontend | Passed: brand integrity, TypeScript project build and Vite production build |
| `npm.cmd run lint` in frontend | Exit 0; 8 existing warnings in App, CaptionTools, SettingsPage, InteractiveTimeline and StudioPage |
| `npm.cmd test` in frontend | 16 passed; caption/reference/timeline regression tests |
| `python -m pip check` | No broken requirements |
| `npm.cmd ls --depth=0` | All declared frontend top-level dependencies resolved |
| `python -m compileall -q backend/app` | Passed |
| `git diff --check` | Passed; Git emitted line-ending conversion notices |
| `/api/ready` | HTTP 200; storage, FFmpeg and FFprobe true |
| Compose file parsing | YAML parsed with backend and web services; not Docker validation |
| Live OpenRouter / Pixabay credential tests | Both verified successfully outside the network sandbox using saved backend credentials; paid generation not exercised |
| Docker image build and hosting smoke tests | Not run: Docker unavailable; no hosting environment supplied |

Initial attempts and limitations are retained here rather than hidden:

- The first analytics run had 3 setup errors because Windows denied pytest's default
  temporary directory. A unique workspace `--basetemp` resolved them; all six passed.
- The first extra studio/numeric run had 15 setup errors because its test backend did
  not start within 15 seconds under load. The fixture now allows up to 60 seconds.
- The expanded legacy browser run recorded 5 failures and 15 setup errors. It exposed
  stale landing-button/reload assumptions, old command-placeholder and export-heading
  assertions, plus startup delays under load. The tests now enter `#/studio`, retain
  editor state on reload, use the current accessible labels, and choose local commands
  for deterministic editing tests. An intermediate rerun passed its first test and
  stopped at one remaining stale placeholder; that assertion was corrected too.
- The next editor rerun passed layout/reload and the complete Auto Reel/command/MP4
  workflow, then stopped at the old `Transcribe` label. The test now uses `Generate
  speech captions` and waits for actual model verification. A five-second readiness
  assertion was also too short for cold CPU inference; it now has a bounded 120-second
  wait. Numeric undo checks restore the measured initial font size instead of assuming
  the old 42px caption default.
- An external-provider retest requesting execution outside the restricted network was
  **not executed**: automatic approval review returned HTTP 503 Service Unavailable.
  This was a review-service failure, not a determination that the action was unsafe.
- After the approval service recovered, the approved external-provider retest succeeded
  for both OpenRouter and Pixabay. Their initial sandbox connection failures are not
  outstanding credential failures.
- Mocked credential/error tests verify reporting logic; they are not evidence that
  either cloud provider generated content. The separate live tests above did verify
  the saved credentials, without returning secrets or account data to the browser.
- The Windows System.Speech fixture initially failed with a NullReferenceException
  inside the sandbox. Creating the same short spoken WAV outside the sandbox succeeded.
  Caption browser tests can reuse that real fixture via `RAYFLOW_TEST_SPEECH_FIXTURE`.
- The existing Pydantic warning comes from a legacy test placing dictionaries directly
  into the transition list. Frontend lint warnings are not build failures.

## Run and deploy

Complete local commands, environment variables, model setup, production build and
deployment instructions are in [deployment.md](deployment.md). For an existing setup:

```powershell
backend/venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
# Second terminal:
cd frontend
npm.cmd run dev -- --host 127.0.0.1
```

Start Ollama, open Connections, reconnect, select an installed model, save and test
the model. No API key is required for Ollama, editing or FFmpeg export. Speech requires
a cached Whisper model. Credentials remain backend-only.

To repeat the backend checks without mixing test jobs with user history:

```powershell
$testRun = Join-Path (Get-Location) ('test_artifacts/check-' + [guid]::NewGuid().ToString('N'))
$env:RAYFLOW_STORAGE_DIR = Join-Path $testRun 'storage'
$env:RAYFLOW_ENV = 'test'
$env:PYTHONUTF8 = '1'
$testFiles = rg --files tests -g 'test_*.py' -g '!test_*browser.py'
backend/venv/Scripts/python.exe -m pytest @testFiles -q --basetemp (Join-Path $testRun 'pytest')
backend/venv/Scripts/python.exe tests/run_browser_checks.py
```

Run this in a separate test terminal; unset the test environment variables before
starting your normal development backend. The browser runner creates and stops its
own services. The standalone Kage scene comparison and personal-reference comparison
scripts are not part of the required regression set; their assets/environment must
be supplied explicitly. Current landing links, loading and responsive behavior are
covered by the production-preview suite.

## Remaining deployment requirements

Validate Linux image resolution/build, Caddy authentication/TLS, mounted-volume
ownership, backups and private model networking on the real host before publication.
The service has no multi-user project authorization, distributed queue or automatic
job replay. Use one backend process/replica behind authenticated ingress. Media and
SQLite need persistent volumes; projects remain in browser storage. Interrupted jobs
must be rerun, and disk usage needs monitoring. Optional segmentation needs its model
and runtime provisioned separately. No public deployment readiness is claimed until
those host checks pass.
