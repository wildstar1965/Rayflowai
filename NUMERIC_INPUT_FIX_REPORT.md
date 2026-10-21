Numeric input fix — verified October 19, 2026

The completed fix covers all 19 numeric text controls in the current frontend. The workspace already contained a partial migration to `NumericInput` and five browser tests. This work audited that migration, reproduced the original bug, corrected the remaining shared-control defects, and expanded verification without modifying unrelated backend work.

The confirmed root cause was conversion and clamping inside controlled input `onChange` handlers. In the original `CaptionSettings`, `Math.max(10, Math.min(300, Number(e.target.value)))` immediately turned the first digit `1` into `10`. Clearing the field also converted the empty string into zero and then applied the minimum. The same pattern affected typography, tracking, positioning, and timing, and sent intermediate edits into project history. A browser reproduction loaded the committed caption component in isolation and confirmed that selecting `10` and typing `1` displayed `10`.

Caption start/end used a different implementation: uncontrolled `defaultValue`, numeric conversion on blur, and keys containing the current numeric value. Those keys could remount fields when committed timing changed. Their existing migration to controlled drafts with stable segment IDs was retained and verified. The audit found no debounce or prop-synchronization effect causing the confirmed font-size reset.

The shared component keeps the exact draft string during editing, including an empty string, partial decimal, or negative sign. Parent renders do not rewrite it or move the cursor. Blur or Enter validates and commits once; Escape discards the draft. Invalid or empty commits retain the latest committed value and explain the result. Unedited fields follow committed props, including undo/redo. Zero is preserved wherever allowed. Adjusted values receive visible feedback.

Step validation now chooses a valid step within both bounds, including when a timing maximum falls between steps. `step="any"` preserves decimal precision without fixed decimal truncation. Parsing and post-arithmetic finite checks prevent `NaN` and `Infinity` commits. Arrow keys edit the draft and share the blur/Enter commit boundary, avoiding a history entry for each keypress. Read-only controls ignore numeric keyboard mutations, and accessibility values reflect the displayed draft.

Relevant implementation files:

| File | Purpose |
| --- | --- |
| `frontend/src/components/ui/NumericInput.tsx` | Shared draft state, commit/cancel behavior, finite/range/step validation, keyboard handling, feedback, and accessibility. Completed and hardened the existing component. |
| `frontend/src/components/studio/CaptionSettings.tsx` | Five consumers; simplified commit handlers to use the shared validated values. |
| `frontend/src/components/studio/CreativePanel.tsx` | Eleven consumers for B-roll, sound timing, and typography. Added explicit accessible names to cinematic start/duration; verified the existing migration. |
| `frontend/src/pages/StudioPage.tsx` | Retained and verified the existing shared-control migration for caption start/end and cinematic color strength. |
| `tests/test_numeric_inputs_browser.py` | Expanded the existing five tests into nine real-browser tests using the repository's pytest/Playwright framework. |
| `NUMERIC_INPUT_FIX_REPORT.md` | Audit and verification record. |

Complete numeric text-control inventory:

| Area | Controls |
| --- | --- |
| Caption appearance (5) | Font size, tracking, phrase characters, phrase seconds, backdrop opacity |
| B-roll (2) | Insert start, insert duration |
| Sound effects (1) | Click time |
| Cinematic typography (8) | Size, tracking, horizontal position, vertical position, fade seconds, entrance scale, start, duration |
| Studio settings and captions (3) | Cinematic color strength, caption start, caption end |

The audit also inspected `EffectsPanel`, `InteractiveTimeline`, other Studio inputs, and export controls. Sound volume, transition durations, total reel duration, timeline zoom, and playhead use native sliders or timeline gestures. Clip trimming uses timeline handles. These controls do not accept partial numeric strings. Font weight uses fixed select options. Export has no numeric text field. Their existing implementations were retained, with zero volume, timeline interactions, rendering, and export covered by regression tests. A final search found no remaining native `type="number"` controls or numeric `value || default`/conversion-fallback patterns in the frontend.

Regression coverage includes selecting `10` and typing `150` one digit at a time; `250`, `1250`, and `999`; middle insertion/deletion and cursor position; clearing and replacement; native clipboard paste; decimals and negatives; zero; min/max and step boundaries; invalid/non-finite input; read-only fields; Escape; grouped arrow edits; prop updates; playback rerenders; changing another setting while a field remains focused; blur followed by a toolbar action; all 19 real field consumers; persisted project state; preview/export request payloads; and undo/redo restoring complete edits. Enter followed by blur is also verified to avoid duplicate commits.

Verification results:

| Command | Result |
| --- | --- |
| `.\backend\venv\Scripts\python.exe -m pytest tests/test_numeric_inputs_browser.py tests/test_studio_browser.py tests/test_sections67.py -q --tb=short` | **36 passed**, no skips, in 134.31 seconds: 9 numeric browser tests, 6 existing Studio browser tests, and 21 typography/caption/service tests. Includes Auto Reel, actual MP4 export, timeline interactions, and prepared speaker-matte preview. |
| `node --test tests/test_timeline_correctness.mjs tests/test_subtitle_timeline.mjs` | **9 passed**. |
| `npm.cmd run build` (from `frontend`) | **Passed**: TypeScript and Vite production build. |
| `npm.cmd run lint` (from `frontend`) | **Exit 0** with four existing warnings: two in `InteractiveTimeline.tsx` and two in `StudioPage.tsx`. No warnings in the shared numeric component or its panel consumers. |
| `git diff --check` | **Passed**. |

No affected numeric text fields or failing tests remain from this audit. Existing field limits still apply on commit: caption size is 10–300 pixels, while cinematic size is 3–30 percent of frame width. Thus `150` can be typed without interruption in both fields; it commits as 150 for captions and adjusts to 30 for cinematic percentage size. Browser verification used headless Microsoft Edge; other browser engines were not run. The four unrelated lint warnings remain.
