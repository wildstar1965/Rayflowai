# Sections 6–7 implementation and verification

19 October 2026. This report covers only cinematic typography, subject-aware text compositing and local subtitles. Existing uncommitted work was retained; unrelated Auto Reel, B-roll, timeline, audio and export architecture was not rebuilt.

## Result

Completed:
- Configurable cinematic headings: local font, size, weight where the font supports it, tracking, alignment, position, case, selected-word color, line breaks, fade and subtle entrance scale. Auto Reel skips brief greetings when selecting display phrases.
- Shared, frame-based title rasters and subtitle events for browser preview and FFmpeg MP4 export. All existing caption presets use the shared layout, including safe wrapping.
- Genuine video-derived person masks. The title alpha is multiplied by the inverse matte, preserving the underlying speaker pixels. Masks follow source trims at 30 fps and the selected fit/fill composition.
- RVM recurrent inference with cached models, atomic mask publication, cancellation, failed-job cleanup and source-matte reuse across aspect ratios.
- Local Faster-Whisper transcription, language/model settings, word timestamps, honest segment-only fallback, content-based transcript caching, changed-source invalidation, source/clip association and bounded background jobs.
- Editable caption text, timing, appearance and emphasis through existing undo/redo state. Manual captions have no fabricated word times. New captions use available intervals inside the project; timing edits clamp against neighbouring captions.
- Missing-model diagnostics and explicit setup commands. No model is downloaded at application startup.
- Focused tests, regression tests, real speech inference, moving-subject MP4 rendering, frame inspection and browser preview/export comparison.

Partially verified / limitations:
- The typography and matte paths share content and timing, but the entire preview is not pixel-identical to MP4. The existing renderer applies FFmpeg color grading that the browser only approximates. The final full-frame browser comparison at 2 seconds measured about 8.9 RGB levels of mean error on a 0–255 scale. This continuation did not rewrite the unrelated grading system.
- Tiny and base transcribe real speech but can misrecognize names and technical terms. Both did so in the supplied four-second sample. Manual correction is necessary for those words; no accuracy percentage is claimed.
- Hair and soft boundaries remain model estimates. Fast motion, occlusions, multiple people and difficult backgrounds can need review. Large text can become mostly obscured when the subject fills a square/landscape crop; position/size and the existing Fit control remain editable.
- CPU inference, the installed RVM model and short real clips were verified. GPU execution, production-length memory stress, broad multilingual accuracy and every optional U2Net configuration were not exercised.
- Cancellation is cooperative between model segments/frames. A native inference call already in progress must return before its worker exits.
- Persistent transcript/raster/mask caches have no automatic disk quota. Browser raster references are limited to approximately 128 MiB of decoded RGBA pixels, excluding browser video/graphics allocations.
- Anton has one native weight. Select Arial or DejaVu Sans for a native regular/bold choice. Installed-font fallback is shared by preview/export on the same backend, but different machines may choose different fallback fonts.
- Segment-only transcription retains the model's full phrase interval. Duration-based phrase splitting and spoken-word highlighting require genuine word timestamps.
- Optional deletion of earlier debug FFconcat manifests was not executed: automatic approval review returned HTTP 503 (review service unavailable). This was a review-service failure, not an unsafe-action finding. Small earlier temporary manifests remain; the renderer now cleans its new manifests automatically.

Uncompleted core features: none identified in this scope. The validation limits above remain; this is not a claim of exhaustive hardware or media coverage.

## Audit and baseline

The initial working tree already contained the typography, speech and segmentation services alongside extensive earlier changes. The audit traced uploaded media through Auto Reel/transcription into EditingPlan, timeline history, preview, and the existing FFmpeg renderer.

Available dependencies were Faster-Whisper 1.2.1, ONNX Runtime 1.23.2 and Pillow 12.3.0. Tiny/base Whisper caches, RVM MobileNetV3 weights, U2Net weights, local Arial/Impact fonts and bundled Anton were present. Anton's existing SIL OFL file was retained. No dependency or model download was needed during this task.

The reference was located at:
C:\Users\tejar\Downloads\WhatsApp Video 2026-10-18 at 9.33.41 AM.mp4

Frames at 0, 1, 2 and 3 seconds were inspected. They show tall condensed uppercase headings, warm emphasis, compact body captions, a top-weighted hierarchy and real head occlusion. The audit contact sheet is [reference-audit.png](test_artifacts/reference-audit.png).

The separate source used for real inference and rendering was:
C:\Users\tejar\Downloads\WhatsApp Video 2026-10-18 at 8.28.04 AM.mp4

Baseline:
- 60 targeted backend/render tests passed, with two existing Pydantic serializer warnings.
- Six timeline tests passed.
- Frontend production build passed.
- The first pytest invocation had 16 fixture setup errors because its default Windows temporary directory was inaccessible. A fresh workspace --basetemp resolved them.
- PowerShell's execution policy blocks npm.ps1 here; npm.cmd works without changing that policy.

## Exact files changed in this continuation

| File | Change |
| --- | --- |
| [.env.example](.env.example) | CPU/compute/provider and mask-resolution configuration examples. |
| [backend/app/schemas/editing_plan.py](backend/app/schemas/editing_plan.py) | Extend existing caption/title styling and source fingerprint fields. |
| [backend/app/services/speech_transcription.py](backend/app/services/speech_transcription.py) | Local-model settings, sanitized diagnostics, cancellation, cache publication, source identity, valid intervals and job lifecycle. |
| [backend/app/services/processing.py](backend/app/services/processing.py) | Shared cooperative cancellation exception/check. |
| [backend/app/api/routes.py](backend/app/api/routes.py) | Pass language/model configuration and expose transcription cancellation. |
| [backend/setup_local_assets.py](backend/setup_local_assets.py) | Explicit opt-in Whisper cache setup command. |
| [backend/app/services/auto_edit.py](backend/app/services/auto_edit.py) | Content-aware transcript reuse, refresh changed sources without rebuilding the timeline, retain manual corrections, attach sources and propagate cancellation. |
| [backend/app/services/caption_frames.py](backend/app/services/caption_frames.py) | Shared sentence-aware caption events, source-clock mapping, safe font layout, real word highlighting and one FFmpeg caption stream. |
| [backend/app/services/cinematic.py](backend/app/services/cinematic.py) | Local font fallback, measured title layout, shared animated rasters and lossless frame-track manifests. |
| [backend/app/services/video_renderer.py](backend/app/services/video_renderer.py) | Consume shared title/caption streams in existing export; retain real matte occlusion and audio; cancellation and manifest cleanup. |
| [backend/app/api/creative_routes.py](backend/app/api/creative_routes.py) | Serve shared title frames/configuration and expose mask-job cancellation. |
| [backend/app/services/creative_jobs.py](backend/app/services/creative_jobs.py) | Cooperative cancellation for existing local work queue. |
| [backend/app/services/segmentation.py](backend/app/services/segmentation.py) | Configurable mask quality/provider, atomic preparation, cleanup, source metadata and reuse inference across framing changes. |
| [frontend/src/types/index.ts](frontend/src/types/index.ts) | Mirror the extended editing-plan fields. |
| [frontend/src/components/studio/useCreativePreview.ts](frontend/src/components/studio/useCreativePreview.ts) | Consume shared raster frames, prevent stale asynchronous results, preload nearby frames and bound decoded image memory. |
| [frontend/src/components/studio/CaptionSettings.tsx](frontend/src/components/studio/CaptionSettings.tsx) | Caption typography, phrase limits, position and spoken-word highlighting controls. |
| [frontend/src/components/studio/CreativePanel.tsx](frontend/src/components/studio/CreativePanel.tsx) | Cinematic typography controls and cancellable subject-mask preparation. |
| [frontend/src/pages/StudioPage.tsx](frontend/src/pages/StudioPage.tsx) | Transcription controls/source mapping, safe editable captions, existing history integration and shared caption preview. |
| [frontend/src/utils/subtitles.ts](frontend/src/utils/subtitles.ts) | Source-to-timeline mapping and bounded non-overlapping manual caption intervals. |
| [frontend/src/services/api.ts](frontend/src/services/api.ts) | Transcription language/model arguments and cancelled-job handling. |
| [tests/test_sections67.py](tests/test_sections67.py) | Deterministic typography, transcription, invalidation, cancellation, real FFmpeg frame alignment and native-matte reuse tests. |
| [tests/test_subtitle_timeline.mjs](tests/test_subtitle_timeline.mjs) | Trim/reorder source mapping and manual timing regressions. |
| [tests/test_studio_browser.py](tests/test_studio_browser.py) | Extend existing controls tests and compare real subject preview with MP4; exercise moving preview. |
| [tests/verify_sections67.py](tests/verify_sections67.py) | Opt-in real speech/matte/export verification and measured occlusion comparison. |
| [SECTIONS_6_7_REPORT.md](SECTIONS_6_7_REPORT.md) | This continuation's setup, evidence and limitations. |

Other files already marked modified/untracked before this task remain part of the user's earlier work. Generated verification media is under the already-ignored test_artifacts directory.

## Setup and execution in Windows PowerShell

On this machine, the required environments, fonts and model weights already exist. These commands document reproducible setup for a fresh installation.

~~~powershell
Set-Location 'C:\Users\tejar\OneDrive\Desktop\Rayflow.ai'
if (-not (Test-Path '.\backend\venv\Scripts\python.exe')) {
    py -3.10 -m venv backend\venv
}
.\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-segmentation.txt -r tests\requirements.txt
~~~

Run downloads explicitly only if the corresponding local assets are missing. Whisper tiny is also used by the existing transcription smoke test; base is an optional quality/speed choice.

~~~powershell
.\backend\venv\Scripts\python.exe backend\setup_local_assets.py --whisper tiny
.\backend\venv\Scripts\python.exe backend\setup_local_assets.py --whisper base
.\backend\venv\Scripts\python.exe backend\setup_local_assets.py --video-matting
~~~

Configuration contains no required cloud API key for these features:

~~~powershell
$env:WHISPER_MODEL = 'base'
$env:WHISPER_LOCAL_ONLY = 'true'
$env:WHISPER_DEVICE = 'cpu'
$env:WHISPER_COMPUTE_TYPE = 'int8'
$env:PERSON_SEGMENTATION_MODEL = 'backend/models/rvm_mobilenetv3_fp32.onnx'
$env:PERSON_SEGMENTATION_PROVIDER = 'CPUExecutionProvider'
$env:PERSON_MASK_MAX_SIDE = '960'
$env:PERSON_INFERENCE_MAX_SIDE = '960'
.\backend\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
~~~

Use a second PowerShell terminal:

~~~powershell
Set-Location 'C:\Users\tejar\OneDrive\Desktop\Rayflow.ai\frontend'
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1 --port 5173
~~~

Open http://127.0.0.1:5173. Use Captions to select the speech source/model/language and generate or edit captions. Use Inserts → Cinematic typography for display text and Text behind speaker. Prepare masks again after source trimming or framing changes. Until valid masks are available, the preview does not substitute an unmasked title for an enabled behind-speaker effect, and export reports the missing preparation.

Optional GPU settings require compatible installed runtimes. Set WHISPER_DEVICE/WHISPER_COMPUTE_TYPE and PERSON_SEGMENTATION_PROVIDER accordingly; CPU remains the verified configuration. No GPU package is required.

## Test results and commands

- Full backend suite: **86 passed**, two existing Pydantic serializer warnings, 180.31 seconds.
- Final caption/typography/render follow-up: **25 passed**, 24.52 seconds.
- Final display-phrase and creative-feature follow-up: **59 passed**, 6.59 seconds, including the greeting-selection fix.
- Full browser regression suite: **6 passed**, 108.55 seconds.
- Timeline/subtitle JavaScript tests: **9 passed**.
- Production TypeScript/Vite build: **passed**.
- Lint: **zero errors, four existing warnings**, concerning InteractiveTimeline effects and StudioPage state/purity rules.
- Real tiny/base speech inference: **passed**, with word timestamps and the recognition limitations above.
- Real RVM occlusion and all three MP4 inspections: **passed**.
- Additional moving-subject browser playback and reset check: **1 passed**, five unrelated tests deselected, 16.15 seconds.

Use a new temporary suffix for each pytest run:

~~~powershell
Set-Location 'C:\Users\tejar\OneDrive\Desktop\Rayflow.ai'
$testRun = [guid]::NewGuid().ToString('N')
.\backend\venv\Scripts\python.exe -m pytest tests --ignore=tests/test_studio_browser.py -q "--basetemp=test_artifacts/backend-$testRun"
.\backend\venv\Scripts\python.exe -m pytest tests/test_studio_browser.py -q "--basetemp=test_artifacts/browser-$testRun"
node --test tests/test_subtitle_timeline.mjs tests/test_timeline_correctness.mjs
Push-Location frontend
npm.cmd run build
npm.cmd run lint
Pop-Location
~~~

Browser tests use the installed Microsoft Edge and start isolated local services on unused ports. They do not depend on or stop the user's development servers.

## Real media verification and performance

Reproduce the supplied-source check:

~~~powershell
.\backend\venv\Scripts\python.exe tests\verify_sections67.py 'C:\Users\tejar\Downloads\WhatsApp Video 2026-10-18 at 8.28.04 AM.mp4'
.\backend\venv\Scripts\python.exe tests\inspect_export.py test_artifacts\sections67\9x16.mp4
.\backend\venv\Scripts\python.exe tests\inspect_export.py test_artifacts\sections67\1x1.mp4
.\backend\venv\Scripts\python.exe tests\inspect_export.py test_artifacts\sections67\16x9.mp4
~~~

| Output | Dimensions | Duration / frames | Native-mask preparation | Export |
| --- | --- | --- | --- | --- |
| [Portrait](test_artifacts/sections67/9x16.mp4) | 1080×1920 | 4.000 s / 120 | 42.109 s | 32.781 s |
| [Square](test_artifacts/sections67/1x1.mp4) | 1080×1080 | 4.000 s / 120 | 4.500 s, reused inference | 22.000 s |
| [Landscape](test_artifacts/sections67/16x9.mp4) | 1920×1080 | 4.000 s / 120 | 3.906 s, reused inference | 32.781 s |

All three contain H.264 video and AAC audio, decode fully, and have uniformly spaced 1/30-second timestamps. Export audio RMS was 0.0747. Export dimensions/framing were validated by the existing renderer. Measurements were taken locally while other checks could run; they are not isolated throughput benchmarks.

Cold tiny inference for the four-second excerpt took approximately 4.9 seconds; base took 5.688 seconds. Cached transcript reads took below 0.04 seconds. Ready-mask lookup took 0.016–0.032 seconds. Before native-matte reuse, changing ratio repeated approximately 41–45 seconds of inference; afterward, only 4 seconds of mask reframing was needed, without dropping frames or reducing export resolution.

The actual [occlusion comparison](test_artifacts/sections67/occlusion-comparison.png) shows the base video, unmasked control and subject-masked export. Across 39,900 opaque subject pixels under the title, average RGB error against the base video was **1.156**, versus **154.040** for the unmasked control. Typography remained visible across 59,213 background pixels. Masks at different timestamps differed as the speaker moved.

The final MP4s, portrait/square rendered frames, preview screenshot and contact sheets were inspected. The shared preview uses the same title/caption rasters as export; tests compare those assets as well as an independently encoded frame after seeking.

Evidence:
- [Rendering, transcript, timing and occlusion measurements](test_artifacts/sections67/verification.json)
- [Portrait metadata and timestamp verification](test_artifacts/sections67/9x16.inspection.json)
- [Square metadata and timestamp verification](test_artifacts/sections67/1x1.inspection.json)
- [Landscape metadata and timestamp verification](test_artifacts/sections67/16x9.inspection.json)
- [Preview comparison](test_artifacts/sections67/preview-comparison.json)
- [Browser preview screenshot](test_artifacts/reference-preview.png)
- [Actual subject mask](test_artifacts/sections67/subject-mask.png)
- [Base-model transcript](test_artifacts/sections67/base-transcription.json)

No new secrets were added to code or the report. No remote transcription or paid font service was introduced.
