# Export validation and uploaded duration fixes

Implemented in the existing application. Pre-existing source edits were retained.

## Root causes

- A transition had a minimum allowed length of 0.1 seconds even when an adjacent clip was shorter. In the reproduced six-clip case (0.51, 0.51, 0.1, 0.51, 0.066, 0.37 seconds), that invalid overlap broke the chained xfade/concat output. At 1920x1080, the timeline expected 62 frames but FFprobe actually decoded 51: video ended at 1.70 seconds while audio continued to 2.07 seconds. The prior final-frame padding did not fix the cause.
- Rendering mixed cumulative frame rounding, microsecond transition timestamps, a separately hardcoded validator FPS, and a final duration rounded to hundredths. These calculations did not share one exact frame clock. MP4 packet counts alone also do not prove that every packet is a displayed/decoded frame.
- First-upload timelines distributed a default target duration across videos as if they were images. Appended videos used `min(10, duration || 3)`. Timeline recalculation rounded all durations to hundredths and imposed a 0.5-second minimum. Project/schema caps and Auto Edit's 120-second cap/default speech tightening added other implicit edits. Metadata came from FFmpeg's rounded console banner.

The original failure's commands and FFprobe results are retained in [baseline-failure-evidence.json](test_artifacts/export_duration_fix/baseline-failure-evidence.json); the reproduced failing plan is in [failing-plan.json](test_artifacts/export_duration_fix/failing-plan.json).

## Implemented behavior

- FFprobe JSON supplies precise stream durations and timestamps. The initial video source range begins at zero and includes the full A/V presentation, including audio offsets/tails. VFR duration is never estimated from nominal FPS. Unknown/invalid durations fail instead of using a placeholder.
- Timeline/source durations keep their original precision. Existing order, source trims, clip IDs and transitions survive timeline initialization. Appending, reordering, pacing changes, and default Auto Edit preserve video ranges. Images retain the photo-duration behavior; mixed/appended images use the existing 2.5-second default. Explicit trims remain supported, and video trim controls use source limits instead of the old 30-second control cap.
- Exports use a single 30 fps clock with half-up rounding of cumulative clip boundaries. Transition overlap is bounded by both neighboring clips. Concat/xfade use frame time bases, with explicit encoder time bases and CFR metadata. VFR sources are sampled by timestamp. Audio uses the same clip boundaries at 48 kHz and retains source-relative offsets.
- Removed final padding/frame-count trimming. The final `-t` is the exact frame-grid duration, needed to bound looping overlay inputs; it is no longer rounded to hundredths. Invalid source overruns fail instead of becoming frozen footage. Source decoder errors fail the render.
- Validation checks stream geometry, FPS, start time, stream duration, A/V timing, FFprobe's decoded frame count, and an independent full FFmpeg A/V decode with passthrough timestamps. A negative test confirms that a one-frame mismatch is still rejected.

## Actual-media results

All exports below were checked with FFprobe `-count_frames`, individual decoded frame timestamps, and raw FFmpeg frame decoding. Timestamps are uniformly spaced at 1/30 second. The audio tests compare encoded tone onsets with visible timing markers, including a deliberate 0.237-second source trim and a 0.2-second audio offset.

| Case | Timeline seconds | MP4 video seconds | Decoded frames | CFR rounding (ms) |
|---|---:|---:|---:|---:|
| Single 25 fps video | 2.280000 | 2.266667 | 68 | -13.333 |
| Single VFR video | 2.400000 | 2.400000 | 72 | +0.000 |
| Video over 120 seconds | 121.233333 | 121.233333 | 3637 | +0.000 |
| 29.97 / 25 / 60 fps + VFR, transitions, overlays, source trim | 6.661167 | 6.666667 | 200 | +5.500 |
| Previously failing short-clip transition chain | 2.066000 | 2.066667 | 62 | +0.667 |
| Delayed audio and longer audio tail | 2.479333 | 2.466667 | 74 | -12.667 |

Rounding is separate from trimming: the editable source ranges remain unchanged. A 30 fps output rounds the total endpoint to the nearest frame (up to 16.667 ms); individual clip lengths can differ by up to one frame because their cumulative boundaries are rounded. AAC container durations in these tests differ from video by less than 1 ms. This is not the reproduced 11-frame loss.

Per-export JSON reports, source-clock evidence, and the downloaded browser MP4 are under [test_artifacts/export_duration_fix](test_artifacts/export_duration_fix).

## Files changed for these fixes

- `backend/app/core/config.py`, `backend/app/services/media.py`: FFprobe discovery and precise metadata.
- `backend/app/services/frame_timing.py`, `backend/app/services/video_renderer.py`: one frame clock, valid transitions, VFR/source audio handling, and strict decoded-output validation.
- `backend/app/services/timeline_builder.py`, `backend/app/api/routes.py`: full initial ranges and preservation of existing edits.
- `backend/app/schemas/editing_plan.py`, `backend/app/api/creative_routes.py`: source-duration field and removal of temporal 120-second caps, including overlay placement on longer timelines.
- `backend/app/services/auto_edit.py`, `command_interpreter.py`, `typed_commands.py`: preserve precise ranges and long timelines; speech trimming defaults off and remains opt-in.
- `frontend/src/utils/timeline.ts`, `frontend/src/types/index.ts`, `frontend/src/pages/StudioPage.tsx`, `frontend/src/services/api.ts`, `frontend/src/components/studio/InteractiveTimeline.tsx`: preserve uploaded duration, reorder precision, source-aware explicit trims and defaults.
- `tests/test_export_duration.py`, `tests/test_export_duration_browser.py`, `tests/test_timeline_correctness.mjs`: actual-media and browser regressions.
- `backend/tools/README.md`, `.gitignore`, `LICENSE`: FFprobe installation instructions and license. The locally installed executable is ignored by Git. No Python/npm dependencies were added.

## Verification

- `pytest tests/test_export_duration.py`: **9 passed** (89.79 seconds).
- `pytest tests/test_renderer.py tests/test_render_audit.py tests/test_creative_render.py tests/test_subtitles_export.py`: **10 passed**.
- `pytest tests/test_backend.py tests/test_commands.py tests/test_audit_regressions.py`: **12 passed**; two existing Pydantic warnings from dictionary transition fixtures.
- `node --test tests/test_timeline_correctness.mjs tests/test_subtitle_timeline.mjs`: **10 passed**.
- Selected existing Studio tests for layout, trim/undo/reorder, video-only Auto Edit, seeking and playback: **2 passed**.
- `pytest tests/test_export_duration_browser.py`: **2 passed**; real upload/append/reorder/trim/undo/reload plus MP4 export, download, and playback through the end.
- `npm.cmd run build`: **passed** (TypeScript and Vite).
- `git diff --check`: **passed**.

Tools: bundled FFmpeg 7.1; FFprobe 9.0.2 from the approved Gyan essentials download; headless Microsoft Edge for browser tests. Test temporary directories were isolated inside the workspace.
