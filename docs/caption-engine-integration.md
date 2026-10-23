# Caption Engine integration

Current caption quality, model defaults and verification are documented in
[Caption quality repair](caption-quality-repair.md). The report below records the
earlier integration; its Tiny/Base setup defaults are superseded by that repair.

## Inspection and implementation plan

Source inspected: the local `caption-engine` repository (TypeScript CLI, no web
application). Target: Rayflow's React 19 / TypeScript / Vite frontend and FastAPI
backend. The existing working tree contains unrelated changes; these are retained.

1. Adapt the source cue grouping to Rayflow's `SubtitleSegment` and shared caption
   renderer: word/character/duration limits, pauses, Indic sentence endings, minimum
   display duration, and non-overlapping intervals.
2. Keep faster-whisper, FFmpeg extraction, caching, cancellation and background jobs.
   Validate supported models/languages/files; expose real progress and detected
   language. Preserve manually edited captions when regenerating a source.
3. Add subtitle export and Caption Engine JSON import using existing API patterns.
   Use editor timeline timestamps for exports and source timestamps for imports.
4. Reuse the dependency-free Devanagari and Kannada romanizers in the caption UI;
   preserve English, punctuation, word times, and undo history. Adapt script-aware
   Noto font selection to Pillow's existing renderer, with complex-script shaping.
5. Extend the native Captions panel, then run unit, API, browser and rendering tests.

## Feature mapping

| Source feature / implementation | Existing Rayflow equivalent | Decision / target |
| --- | --- | --- |
| 16 kHz mono extraction, `src/media/extract.ts` | FFmpeg in `speech_transcription.py` | Reuse Rayflow; temporary audio stays local and is cleaned up |
| Local Whisper helper, `scripts/whisper-transcribe.py` | Cached faster-whisper with VAD and word timestamps | Retain working engine, improve validation and progress |
| Cue grouping, `src/captions/group.ts` | Character/duration grouping in `caption_frames.py` | Adapt pauses, word limit, Indic punctuation and minimum cue duration |
| Word windows / active highlighting, `src/captions/active.ts`, `ass.ts` | Shared PNG captions for preview and export | Retain genuine timings and extend subtitle export to shared cue units |
| SRT / ASS, `src/captions/ass.ts`; transcript JSON in `src/cli/run.ts` | Internal ASS helper; no subtitle download UI | Add SRT, VTT, ASS and editable JSON downloads plus source transcript import; VTT is a justified extension |
| Devanagari and Kannada Roman output, `src/transliterate/devanagari.ts`, `kannada.ts` | None | Reuse pure rules behind a Rayflow caption-edit adapter; no API calls |
| Script fonts and shaping, `src/text/fonts.ts`, `script.ts`, `shaper.ts`; `assets/fonts/` | Pillow with limited system-font selection | Adapt bundled Noto fonts to Pillow/RAQM; share rendered PNGs between player and FFmpeg |
| Styling/presets, `src/captions/style.ts` | Font, weight, size, colors, position, background, safe area, emphasis | Extend existing controls; retain Rayflow presets |
| Bounded overlay rendering, `src/render/chunker.ts`, `pipeline.ts` | Single streamed ffconcat caption track | Retain Rayflow's bounded-input renderer rather than add a Node render service |
| Fingerprints / atomic outputs, `src/config/fingerprint.ts`, `render/validate.ts` | Source hash, transcript cache, validated render jobs | Retain and extend for imported/edited captions |
| ElevenLabs Scribe v2 / Deepgram Nova-3, `src/asr/elevenlabs.ts`, `deepgram.ts` | Local Whisper | Defer paid live adapters; import their Caption Engine transcripts including speaker metadata instead |
| Sarvam STT, `src/asr/sarvam.ts` | Local Whisper | Defer: source explicitly lacks reliable word timestamps for this adapter |
| Sarvam/HTTP transliteration, `src/transliterate/providers.ts`, `batching.ts` | None | Defer paid/custom services; local rules and imported Roman text remain available |
| Translation | Sarvam source mentions modes but does not implement a complete translation workflow | Do not advertise translation; romanization changes script, not meaning |
| Speaker identification | Provider word `speakerId`, no local diarization | Preserve imported speaker labels; do not claim local speaker detection |
| Punctuation/capitalization | Whisper text already includes it | Preserve provider output and allow manual corrections; no invented AI correction pass |
| Auto Trim / filler review, `src/autotrim/*` | Existing speech tightening / timeline edits | Retain existing workflow; caption generation must not cut media |
| Prosody styles / entrance animation, `src/media/prosody.ts`, `captions/tone-style.ts`, `animation.ts` | Emphasis and active-word color | Defer prosody-driven animation; avoid a second rendering pipeline |
| Clip scoring / vision, `src/clips/*`, `src/media/video-analysis.ts` | Existing Auto Reel / B-roll | Out of caption-integration scope; retain existing editing features |

The source registry lists 14 languages, with 13 rendering entries marked verified
and Urdu explicitly untested. These are source claims, not guarantees for Rayflow.
Whisper language availability and Indic rendering quality are reported separately.
There is no existing authentication or server project database in Rayflow: editor
plans use localStorage and undo history. This integration follows that model.

Implementation details, setup commands, file inventory and test results follow below
as the work is verified.

## Architecture and data flow

The Captions tab uses the existing uploaded media and `EditingPlan`. A generation
request starts a background transcription job; FFmpeg extracts mono audio when
needed, faster-whisper supplies genuine word times, and the adapted grouping rules
produce editable phrases. Polling reports job stage, progress and detected language.
Temporary extraction audio is removed on success, cancellation and failure;
transcript and raster caches remain available for reuse.

The frontend maps source times through trimmed/repeated timeline clips. Generated
captions replace generated captions from that source while retaining manual edits
and other sources. If the plan changes while generation/import is running, the
result is not applied over the newer plan. Caption edits use the existing history
and localStorage persistence; no separate project service or database was added.

Preview requests and MP4 rendering both use `caption_frames.py` and its cached PNG
overlays. Font selection routes supported Indic scripts to the bundled Noto family
and Pillow/RAQM shaping. Subtitle documents use the same caption windows; SRT/VTT
collapse repeated highlighting states, ASS retains style/word states, and JSON
retains the editable caption track. Export does not alter source media.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/transcribe` | Start local speech job with uploaded filename, model and optional language |
| `GET /api/transcribe/{job_id}` | Retrieve status, progress and generated captions |
| `POST /api/transcribe/{job_id}/cancel` | Cancel queued/running work |
| `GET /api/captions/capabilities` | Report local models, languages, formats and shaping support |
| `POST /api/captions/import` | Convert a word-timed Caption Engine transcript for an uploaded source |
| `POST /api/captions/validate` | Validate an editable Rayflow caption document |
| `POST /api/captions/export/{srt,vtt,ass,json}` | Download a validated caption track; accepts `aspect_ratio` query parameter |
| `POST /api/cinematic/captions` | Build shared preview caption events |
| `POST /api/render` | Existing background MP4 renderer, including the caption track |

## File inventory and preservation

Already present at handoff, retained during completion:

- Backend additions: `backend/app/api/caption_routes.py`,
  `backend/app/schemas/captions.py`, `backend/app/services/caption_engine.py`,
  `caption_documents.py`, `caption_fonts.py`, and
  `backend/assets/fonts/caption-engine/` (20 fonts and `NOTICES.md`).
- Backend integration in existing files: `backend/app/main.py`,
  `backend/app/api/routes.py`, `creative_routes.py`,
  `backend/app/schemas/editing_plan.py`, `backend/app/services/caption_frames.py`
  and `speech_transcription.py`.
- Frontend additions: `frontend/src/components/studio/CaptionTools.tsx`,
  `frontend/src/utils/romanizeCaptions.ts` and
  `frontend/src/utils/captionEngine/{devanagari,kannada}.ts`.
- Frontend integration in existing files: `frontend/src/pages/StudioPage.tsx`,
  `frontend/src/components/studio/CaptionSettings.tsx`,
  `frontend/src/services/api.ts`, `frontend/src/types/index.ts` and
  `frontend/src/utils/subtitles.ts`.
- Existing verification/configuration: `tests/test_caption_engine.py`,
  `tests/test_caption_engine.mjs`, `tests/test_sections67.py`, `.env.example`
  and the feature mapping above.

Completion work changes only this document and verification files:

- Corrected two unfinished assertions/fixtures in `tests/test_caption_engine.py`:
  create long captions with valid enclosing timestamps, and accept legitimate ASS
  override tags between newline escapes and visible text.
- Added `tests/test_caption_engine_browser.py` to exercise actual speech generation,
  editing, regeneration, downloads, import, romanization, persistence and rendering.
- Installed the already-declared `tests/requirements.txt` dependencies into the
  existing `backend/.venv`; no application dependency manifests or `.env` files
  were changed. Unrelated existing modifications/deletions were retained.

## Windows setup and run commands

Run PowerShell from the Rayflow repository root. Reuse the existing Python 3.10
environment on this workstation. On a fresh machine with Python 3.10 registered
with the launcher, create it only if absent:

```powershell
if (-not (Test-Path -LiteralPath '.\backend\.venv\Scripts\python.exe')) {
    py -3.10 -m venv backend/.venv
}
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\backend\.venv\Scripts\python.exe -m pip install -r tests/requirements.txt
Push-Location frontend
npm.cmd ci
Pop-Location
```

FFmpeg comes from `imageio-ffmpeg`. FFprobe is separate: this workstation already
has `backend/tools/ffprobe.exe`. On another machine, place the executable there,
install it on PATH, or set `FFPROBE_PATH` as described in
[`backend/tools/README.md`](../backend/tools/README.md). Retain the bundled font
notices; no system-wide font installation is required for preview or MP4 export.

Caption processing needs no API key. These values can be set in `backend/.env`
without replacing its existing contents:

```dotenv
WHISPER_MODEL=base
WHISPER_LOCAL_ONLY=true
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
MAX_UPLOAD_MB=500
```

The Captions tab's model selector determines its generation request; choose a
cached model (the tab initially selects `tiny`). `WHISPER_MODEL` is also used by
other existing backend workflows. This workstation has tiny, base and medium
cached; no model download was needed for verification. On a fresh machine, cache
the desired model once while connected to the internet:

```powershell
.\backend\.venv\Scripts\python.exe backend/setup_local_assets.py --whisper tiny
```

CPU/int8 runs locally without paid services or a GPU. Larger models need more
memory and processing time. CUDA is optional and requires compatible hardware and
runtime libraries; it was not part of this verification. Leaving
`WHISPER_LOCAL_ONLY=true` prevents an unexpected model download during editing.

Start the API in one terminal:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
Set-Location frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to port 8000. For a different
backend port set `RAYFLOW_API_PROXY_TARGET` before starting Vite. For a separate
frontend/API deployment the actual frontend setting is `VITE_API_BASE_URL`, and
the backend's `CORS_ORIGINS` must permit that frontend origin. The legacy
`VITE_API_URL` entry in `.env.example` is not read by the API client. Credentials
belong only in backend configuration and must never use a `VITE_` prefix.

## Test the caption workflow

1. Open Studio, upload a supported video with speech, and open Captions. Select
   the source, a cached model and optionally a Whisper language code (for example,
   `en`, `hi` or `kn`); leave language empty for detection.
2. Select **Generate speech captions**. Check progress and resulting caption/word
   times. Play the video and seek through the timeline to check highlighting.
3. Edit caption text and timing, change appearance, and use undo/redo. Regenerate
   to verify that manual corrections remain. Editing text that no longer matches
   the recorded words intentionally uses phrase timing instead of invented times.
4. Download SRT, WebVTT, ASS and Editable JSON. Reimport the Rayflow JSON to restore
   the track; that operation replaces the track and is undoable.
5. Import Caption Engine transcript JSON against its uploaded source. Genuine
   ordered word times are required. Optional saved Roman text can be used during
   import. **Romanize captions** converts Devanagari/Kannada locally and supports
   undo; review pronunciation-dependent spellings.
6. Export MP4 and check captions and original audio. Try an invalid language or
   malformed transcript to verify errors leave the current caption track intact.

Automated checks from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_caption_engine.py tests/test_sections67.py tests/test_audit_regressions.py tests/test_creative_features.py tests/test_ai_editing.py tests/test_transcription.py tests/test_subtitles_export.py tests/test_creative_render.py tests/test_render_audit.py tests/test_backend.py -q --tb=short
node --test tests/test_caption_engine.mjs tests/test_subtitle_timeline.mjs tests/test_timeline_correctness.mjs
.\backend\.venv\Scripts\python.exe -m pytest tests/test_caption_engine_browser.py tests/test_studio_browser.py::test_multitrack_insert_caption_sound_controls_and_undo tests/test_studio_browser.py::test_cinematic_preset_and_manual_title_layout -q --tb=short
Push-Location frontend
npm.cmd run build
npm.cmd run lint
Pop-Location
```

The new browser suite starts isolated API/Vite servers on unused ports and shuts
them down afterward. It uses installed Microsoft Edge and Windows System.Speech
to generate a test video, plus the cached tiny model; it does not need an external
speech provider. Windows speech/Edge access may require running outside a
restricted sandbox. Generated test artifacts remain under `test_artifacts`;
the application's persistent upload/export caches retain their normal behavior.

## Known scope limits

- No live ElevenLabs, Deepgram or Sarvam adapter, translation, local diarization,
  prosody animation or clip scoring was added. These exclusions were recorded in
  the original implementation mapping; speaker metadata can be imported.
- Offline romanization covers Devanagari and Kannada only. Other text is preserved.
  Nine Indic font families are bundled, but not every Whisper language has been
  visually reviewed. Urdu/Arabic font fallback and mixed-script typography are not
  guaranteed. RAQM is required for complex-script rendering.
- SRT/VTT contain text and timing; they do not carry editor styling. ASS approximates
  the available styling and depends on the subtitle player's fonts; MP4 uses the
  same raster renderer as Rayflow preview.
- No new italic/shadow controls were added beyond Rayflow's existing style model.
- Caption documents are limited to 20,000 cues; source transcript imports accept
  at most 100,000 words and the UI limits JSON files to 10 MB. Background processing,
  progress, cache and cancellation support longer work, but multi-hour load tests
  and GPU execution were not performed.
- LocalStorage remains the project store; background job state is in memory and
  does not survive a backend restart. Authentication and a server project database
  were not part of the existing architecture or this integration.

## Verification results — 23 October 2026

| Check | Result |
| --- | --- |
| Selected Python unit/API/transcription/render regressions (command above) | 117 passed |
| New caption browser acceptance tests plus existing multitrack/caption and cinematic-preset tests | 4 passed |
| JavaScript caption, subtitle timeline and timeline correctness tests | 13 passed |
| Frontend production build (including TypeScript and existing asset checks) | Passed |
| Frontend lint | Exit code 0; five existing warnings |
| Python dependency consistency (`python -m pip check`) | No broken requirements |

Total: 134 passing checks across the selected automated suites. The backend and
frontend both started successfully in isolated browser-test servers. Actual local
Whisper inference on Windows-generated speech produced words with valid enclosing
caption times, then regeneration preserved a manually edited caption. Extraction
audio cleanup was checked, and the existing suite covers cancellation cleanup and
native error redaction.

The browser downloaded all four subtitle formats, reimported editable JSON,
retained edits after reload, played the video, and imported native Hindi/Kannada
text with speaker metadata. Romanization and undo retained real word times.
Invalid imports left the track intact. Caption controls were accessible at 1440,
768 and 390 pixels wide, using the existing Media toggle on smaller screens.

Native-script burned-in MP4 export retained audible speech. Decoded export frames
were compared with the browser canvas at 1, 2 and 3 seconds. Mean RGB differences
were 4.922, 4.912 and 4.907 on a 0–255 scale, below the 12-point threshold. Separate
glyph masks verified that captions were visible in both outputs, with caption RGB
differences of 9.335 and 9.996 below the 18-point threshold. Hindi and Kannada
preview screenshots were also inspected. Local evidence is retained in
[`test_artifacts/caption-engine/preview-export.json`](../test_artifacts/caption-engine/preview-export.json),
[`preview-1s.png`](../test_artifacts/caption-engine/preview-1s.png) and
[`preview-2s.png`](../test_artifacts/caption-engine/preview-2s.png).

No selected test remains failing. Non-blocking warnings remain in completed code:
five React lint warnings in `CaptionTools.tsx`, `InteractiveTimeline.tsx` and
`StudioPage.tsx`, plus two Pydantic serializer warnings from the existing
`test_backend.py` transition fixtures. Those files/behaviors were not rewritten as
part of finishing verification. This is a selected regression run, not a claim
that every test or optional external-service workflow in the repository ran.

Completion is assessed against the seven phases of the original task and the
feature mapping established before this continuation. All seven are finished;
the deliberately excluded source features remain listed under scope limits.
