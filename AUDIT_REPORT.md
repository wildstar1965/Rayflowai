# RayFlow AI functionality audit — 18 October 2026

The requested audit, repairs, automated validation, and browser-to-MP4 workflow were completed. Existing uncommitted work was retained; no reset or commit was performed. This report distinguishes verified behavior from remaining limitations.

## Main diagnoses and repairs

| Area | Cause found | Change |
| --- | --- | --- |
| MP4 motion jitter | `zoompan` operated on output-sized images, rounding crop coordinates at visible pixel/chroma boundaries. Motion speed depended on frame number rather than clip duration. Pan presets were ignored. | Supersample the crop at 4× resolution in RGB; use bounded, duration-normalized zoom and pan; match preview motion geometry. Motion remains enabled. |
| Transition timing | Each overlap shortened the sequence, and the renderer froze the last image for all accumulated overlaps. Explicitly disabled transitions could fall back to the clip's transition. | Hold the incoming first frame during its transition lead-in, preserving sequential clip starts; honor disabled transitions and real hard cuts. Normalize dimensions, sample aspect ratio, pixel format, FPS, time base, and timestamps. |
| FFmpeg transition failures | Applying `setpts` after `fps` removed constant-frame-rate metadata in the bundled FFmpeg. Chained boundaries could also lose closing frames through rounding. | Reset timestamps before establishing FPS; quantize the final output to the exact timeline frame count, with only bounded frame-rounding padding. Full decoding now checks the exact frame count before marking an export complete. |
| Auto Reel | Bare returned filenames became malformed preview URLs; presets always forced 9:16; duration sometimes came from a fabricated 15-second fallback; audio-only input could become an image clip. Video lacked an upload/preview path. | Resolve and validate uploads, return usable media URLs, preserve the selected ratio, probe real video duration, require visual assets, construct ordered editable clips and transitions, add video upload/preview/source audio support, and expose caption failures as warnings. |
| Landscape controls | Width-based 16:9 sizing had no corresponding height constraint inside shrinking flex containers. | Give the preview its remaining space with explicit minimum sizes; constrain both dimensions while preserving aspect ratio; keep controls from shrinking. Side panels become accessible drawers at narrow widths. |
| Playhead | The needle used `pointer-events-none`; ruler, label, padding, and track origins disagreed. | Add a larger grab target, pointer capture, a preserved grab offset, one seek per animation frame, scroll/zoom-aware mapping, cancellation cleanup, and keyboard seeking. |
| Trim undo | Every live trim updated the plan, then undo saved the already-trimmed state. | Capture the pre-drag plan and commit one history entry; preserve video source offsets when trimming from the left. |

Other fixes include:

- Missing sources now fail explicitly instead of silently rendering a different uploaded image. Corrupt or partially unsupported upload batches fail cleanly.
- Beat analysis no longer fabricates a 120 BPM grid on failure. Audio-analysis cache keys include file modification metadata. Form, JSON, and query requests are supported.
- Timeline construction retains dense asset sets, respects disabled beat sync, and uses ordered minimum-length intervals.
- Adding/removing media preserves unrelated timeline edits. Duration and pacing controls now apply edits rather than only changing metadata.
- Video frames load and seek in the canvas; image load completion repaints paused previews. Source audio is trimmed and padded to its timeline slot.
- Playback stops at the final frame; short soundtracks no longer stop the whole reel early. End seeks do not jump to the first clip.
- Project hydration is protected from an initial local-storage overwrite. Undo/redo keyboard shortcuts work; resetting a project clears its old history.
- Waveform decoding closes AudioContexts and aborts obsolete requests. Poll timers and voice recognition are cleaned up on unmount.
- Common editing commands run through the full deterministic clip grammar before the restricted Ollama update schema. LLM responses cannot claim changes that were not applied. “Disable beat sync” is recognized correctly; generic mentions of “reel” no longer force portrait.
- Caption export uses each segment's own style and exact word intervals rather than the first segment's style and overlapping minimum word durations. Title placement is applied in export.
- Errors remain visible when a side panel is closed. Video-only projects can use the transcription control.
- The external blocking font request was removed; the existing system-font fallback allows the local UI to open without that network dependency.
- Export download waits for completed validation. Rendering failures and unavailable progress endpoints are visible.

## Validation and actual results

| Check | Result |
| --- | --- |
| Consolidated Python suite, excluding browser tests | **24 passed** in 102.11 s |
| Final targeted exact-frame-count and mixed video/audio export tests after tightening validation | **2 passed** in 11.37 s |
| Existing advanced workflow script | Passed its editing commands and real 9:16, 16:9, and 1:1 exports |
| Actual TypeScript timeline utilities, run by Node | **6 passed**; the prior duplicated JavaScript test implementation was removed |
| Headless Edge browser suite | **3 passed** in the final 56.57 s run: layout/timeline/history/persistence/reset, Auto Reel/text edit/export/download, and video-only Auto Reel/seek/play/export |
| Frontend TypeScript and Vite production build | Passed |
| Existing frontend lint | Exit 0, with remaining warnings described below |
| Full MP4 decoding and timestamp inspection | Passed for the downloaded photo and video reels |

The existing advanced and subtitle export fixtures declared durations inconsistent with their clips. Their declared durations were corrected to 4.5 s and 4.0 s respectively. The title command test now checks the spatial value `center`, while title appearance at the beginning is temporal. No timeout was increased to hide failures.

The motion regression tracks a centered feature through 90 generated frames. RMS frame-to-frame centroid movement fell from **0.3723 px** with output-resolution sampling to **0.1678 px** with the corrected filter, a reduction of about **55%**. This measures rounding-induced jitter on a controlled fixture; it does not remove movement already present in a source video.

Browser checks covered **1440×900, 1280×720, 1024×600, 768×600, and 390×650** at all three aspect ratios. They checked control bounds, preview ratio, page overflow, seeking at start/middle/end, dragging with zoom and horizontal scroll, trim undo/redo, stable-ID clip reorder, repeated playback, reload persistence, and project reset. Tests use real local API/Vite processes on unused ports, real uploads, real FFmpeg, and real downloads.

## Verified exported files

| File | Duration / frames | Video | Audio |
| --- | --- | --- | --- |
| `test_artifacts/browser-auto-reel.mp4` | **8.000 s / 240 frames** | **1920×1080, 30 fps, H.264, yuv420p** | AAC stereo; silent because no soundtrack was selected |
| `test_artifacts/browser-video-reel.mp4` | **3.000 s / 90 frames** | **1080×1920, 30 fps, H.264, yuv420p** | AAC stereo with the source test audio |
| Latest path in `backend/storage/exports/audit_verified_export.json` | **4.000 s / 120 frames** | **1920×1080, 30 fps, H.264** | AAC; measured silence in image slots and audible source audio in the video slot |

The downloaded photo reel was generated by Auto Reel, modified through a natural-language command, and exported with the same plan sent by the editor. Both downloaded reels decoded completely with uniformly spaced frame timestamps. Contact sheets and inspection JSON are beside the MP4s; `test_artifacts/studio-landscape.png` records the preview layout. Generated test artifacts are ignored by Git and retained locally for review.

## Files changed in this audit

Paths below include files that already had user changes; only the audit's targeted changes were added.

- `.gitignore`
- `backend/app/api/routes.py`
- `backend/app/schemas/editing_plan.py`
- `backend/app/services/audio_analysis.py`
- `backend/app/services/auto_edit.py`
- `backend/app/services/command_interpreter.py`
- `backend/app/services/media.py`
- `backend/app/services/ollama_client.py`
- `backend/app/services/speech_transcription.py`
- `backend/app/services/subtitles.py`
- `backend/app/services/timeline_builder.py`
- `backend/app/services/video_renderer.py`
- `frontend/index.html`
- `frontend/vite.config.ts`
- `frontend/src/components/studio/EffectsPanel.tsx`
- `frontend/src/components/studio/InteractiveTimeline.tsx`
- `frontend/src/pages/StudioPage.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`
- `tests/requirements.txt`
- `tests/inspect_export.py`
- `tests/test_audit_regressions.py`
- `tests/test_e2e_advanced.py`
- `tests/test_e2e_workflow.py`
- `tests/test_render_audit.py`
- `tests/test_renderer.py`
- `tests/test_studio_browser.py`
- `tests/test_subtitles_export.py`
- `tests/test_timeline_correctness.mjs`
- `AUDIT_REPORT.md`

The user's existing `.env`, `.env.example`, backend requirements, and unrelated IDE files were not edited by this audit. Pytest and Playwright were installed in the existing virtual environment for testing; no production dependency was added.

## Remaining limitations and unverified behavior

- Browser verification used headless Microsoft Edge and mobile viewport emulation. Safari, Firefox, physical touch devices, and microphone permission/voice recognition were not exercised.
- Whisper's real local pipeline completed on the synthetic audio fixture. Transcription quality and timing on real human speech, other languages, and larger models remain unverified.
- Ollama was unavailable in the browser runs. Offline behavior and the deterministic fallback were tested; live model-generated edits were not verified.
- Canvas color grading and some typography/wrapping remain approximate representations of FFmpeg/ASS. Frame timing, clip order, ratio, source seeking, and transition enablement are synchronized, but pixel-identical preview/export rendering is not claimed.
- Browser-native decoding support varies for MOV, AVI, MKV, and unusual codecs. MP4/H.264 was verified. Video overlays and multi-video contextual B-roll were not comprehensively verified; the clearest supported Auto Reel flows are photo montages and a primary talking-head video with image inserts.
- Jobs and their status remain in memory. Restarting the backend interrupts active jobs; durable job recovery and export cancellation are not implemented.
- Lint still reports unused imports/helpers in existing components and React effect/purity warnings. It exits successfully, but the repository is not lint-warning-free.
- Testing used synthetic media and the existing soundtrack fixture. No claim is made that every possible uploaded codec, long caption, or source recording is free of defects.

An approval-service outage briefly prevented redundant checks, and earlier detached development servers interrupted two browser attempts. Final tests were rerun using ordinary workspace access and test-owned servers; those infrastructure interruptions are not counted as successful checks.

## Reproducing checks

From the repository root with the existing virtual environment:

```powershell
.\backend\venv\Scripts\python.exe -m pip install -r tests/requirements.txt
.\backend\venv\Scripts\python.exe -B -m pytest tests --ignore=tests/test_studio_browser.py -q
.\backend\venv\Scripts\python.exe -B tests/test_e2e_advanced.py
node --test tests/test_timeline_correctness.mjs
.\backend\venv\Scripts\python.exe -B -m pytest tests/test_studio_browser.py -q
.\backend\venv\Scripts\python.exe -B tests/inspect_export.py
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
```

The browser suite uses an installed Edge browser (`channel='msedge'`). It starts and stops its own API/frontend processes. Under a restricted Windows sandbox, use a fresh `--basetemp` path inside `test_artifacts` if the system pytest temporary directory is inaccessible.
