# Caption quality repair — 23 October 2026

Rayflow now adapts Caption Engine's stable caption layout and defaults to locally
verified Medium transcription. The repair was compared against the supplied
original video and the source project's generated reel. Existing unrelated working
tree changes, source media, Caption Engine files, and real `.env` files were retained.

## Evidence and root causes

Reference repository: `C:\Users\tejar\OneDrive\Desktop\New folder\caption-engine`.
The inspected sample is `outputs/edited-reel.mp4` (1080×1920, 30 fps, 24.6 seconds).
Its `tmp/transcript.json` identifies faster-whisper Medium and contains 45 words.

The supplied `C:\Users\tejar\OneDrive\Pictures\Camera Roll\WIN_20261021_16_40_31_Pro.mp4`
is byte-for-byte identical to Rayflow's existing upload
`backend/storage/uploads/media_292654431488b86e.mp4`. The original is 1920×1080,
about 24.615 seconds. The comparisons deliberately select Rayflow's 9:16 export
setting to match the source sample; the original file is never rewritten.

The defects were independent and cumulative:

- Tiny was the UI default and produced poorer text on this clip. Choosing a
  different model in Auto Reel could still reuse the previous model's transcript.
- `apply_word_emphasis` assigned heuristic 1.25× sizes. The old caption painter
  vertically centered individual tokens by their glyph bounds, making capitals,
  descenders and emphasized words sit at different heights.
- Font size, outlines and output resolution did not share a consistent scale.
  The original Rayflow captions were visibly too small and low in the comparison.
- Highlight windows ended at individual word ends, leaving gaps before the next
  word. Layout did not reserve stable space for the active word's growth.
- Font selection treated mixed-script tokens as a single script, and punctuation
  fragments such as `B` / `-tech.` could be split into separate cues.

Audio extraction was already appropriate: FFmpeg produces mono, 16 kHz, 16-bit
PCM WAV. Both implementations use faster-whisper with VAD and genuine word
timestamps. No sentence timestamps are divided into invented word times.

## Source functions reused and adaptation

| Caption Engine source | Rayflow implementation |
| --- | --- |
| `src/captions/svg.ts`: `layoutCue`, measured space width, reserved active widths, common baselines, two outline/fill passes | New `caption_layout.py`: `layout_words`, `shaped_runs`, `paint_caption` |
| `src/captions/active.ts`: `activeWordWindows`, `resolveWordStyle` | `caption_engine.active_word_windows` and stable active-word scaling in the shared painter |
| `src/captions/group.ts`: `groupIntoCues`, sentence endings, pause/word/character limits | Existing adapted grouping extended with `timed_words` / `group_text` to preserve joined tokens and punctuation |
| `src/captions/style.ts`, grouping defaults and CLI active-scale default | Noto Sans bold, 72 px at 1920 px height, 6 px outline, white text, `#FFD400` active word, 0.72 lower anchor, four words, 22 characters, 1.08× active scale |
| `src/text/script.ts`, `shaper.ts`, `fonts.ts` | `caption_fonts.script_runs`, bundled Noto fonts and Pillow/RAQM shaping |
| `scripts/whisper-transcribe.py` | Retained Python faster-whisper inference, matching Medium / word timestamps / VAD; added discovery, runtime checks and safe model errors |

These are adaptations of the source algorithms, not an imported TypeScript render
service. Caption Engine shapes glyphs into SVG outlines and builds caption frames
for its FFmpeg pipeline. Rayflow keeps Pillow/RAQM and its bounded FFmpeg frame
track, so the editor preview and burned-in MP4 use the same cached PNGs. It does
not use MoviePy or ASS as the caption raster renderer.

The source Python helper accepts a library model identifier through `--model`,
defaults to Medium, and constructs CPU/int8 Whisper directly. It has no
inference-tested UI catalog or GPU fallback, and model/FFmpeg failures propagate
as process errors. Rayflow therefore supplies those service-level protections
instead of copying the helper wholesale. Large v3 and Turbo use the installed
faster-whisper identifiers; they are not separate custom inference engines.

## Final behavior

Typography uses a shared baseline, measured script runs, at least 0.34 em between
words, 1.38 em line spacing, and reserved word slots. Font size, outline and
tracking scale with frame height. Measured wrapping fits at most two lines inside
the available width; safe bounds keep the caption inside the frame. Outline passes
precede fills so adjacent outlines do not paint over previously drawn text.

Automatic emphasis no longer changes arbitrary word sizes or capitalization.
Active words may grow to the reference's 1.08× size without moving the surrounding
words. The active window lasts until the next word starts; recorded word
timestamps remain unchanged. Grouping respects pauses, punctuation, joined
subwords and the existing duration limits. Captions without word timings retain
phrase timing. Changed manual text does not inherit misleading word alignment.

Noto script selection operates inside mixed-script tokens. Combining marks and
joiners stay with their base characters; codepoint tracking is disabled for
non-ASCII tokens to avoid breaking shaping. RAQM is available on this workstation.

Existing caption text and styles are not automatically reset. **Apply Caption
Engine style** explicitly applies the reference appearance to the caption track
and remains undoable. Regeneration preserves manual captions. Auto Reel records
`transcript_model`, refreshes speech when the chosen model changes, and preserves
the editable timeline. Failed or empty retranscription retains the existing
caption/transcript data and model provenance.

SRT, WebVTT, ASS and editable JSON downloads, transcript import, local romanization,
timeline mapping, cancellation and temporary-audio cleanup remain integrated.
ASS approximates the raster style and depends on the subtitle player's fonts;
SRT/VTT carry text and timing only. MP4 and preview share the exact painter.

## Models and runtime

| UI choice / inference ID | Status on this workstation |
| --- | --- |
| Medium / `medium` | Cached, loaded and inference verified; selected by default |
| Small / `small` | Supported; not cached, disabled |
| Large v3 / `large-v3` | Supported; not cached, disabled |
| Large v3 Turbo / `turbo` | Supported; not cached, disabled |
| Tiny / `tiny`, Base / `base` | Kept for old API callers; removed from the user-facing selector |

The Captions and Auto Reel panels share the model service. `GET /api/captions/models`
reports availability; `POST /api/captions/models/check` starts background local
load-and-inference checks. A cache directory alone does not make a model selectable.
Incomplete, missing, unverified and failed models remain disabled.

Medium is the default even when an old configuration specifies Tiny/Base.
`WHISPER_DEVICE=auto` uses compatible CUDA when detected and CPU otherwise.
Loading or readiness-inference GPU failures fall back to the same model on
CPU/int8 with a visible notice. No Tiny/Base substitution occurs. Insufficient
memory produces an actionable error suggesting an explicit Small selection.
Checks and normal inference use local-only loading, a shared inference lock and a
single cached model; no additional model was downloaded for this repair.

This workstation reports zero CUDA devices. Actual GPU execution, Large v3,
Turbo and Small inference were therefore not verified. GPU loading failure and
memory error handling were tested with simulated failures. CPU processing time
depends on the clip, model, memory and concurrent work.

## Actual comparison

The before-render artifact isolates the old renderer using the saved reference
transcript. The final after-render uses fresh Rayflow Medium inference on the
original video. Tiny/Medium inference is measured separately, avoiding attribution
of transcription differences to typography.

| CPU/int8 measurement | Tiny | Medium |
| --- | ---: | ---: |
| Generated timed words | 41 | 45 |
| Word edits versus 45-word saved ASR reference | 11 | 0 |
| Mean matched word-boundary difference | 0.089 s | 0.0033 s |
| Load plus readiness probe | 3.312 s | 14.859 s |
| Clip inference | 1.516 s | 12.828 s |
| Peak process working set | 265.0 MiB | 1809.6 MiB |

These are one-run measurements, not a general benchmark. Word comparison
normalizes case and punctuation. The saved ASR transcript is not independent
human ground truth; zero edits is agreement, not proof of perfect transcription
or acoustic alignment. Peak working set is a process high-water mark, measured
while running Tiny then Medium in the same process, not isolated model memory.

The final 24.6-second export contains 15 cues, rendered in about 41.86 seconds,
and completed an FFmpeg decode check. Matching frames at 2.4, 8 and 14 seconds
were inspected side by side: the final captions closely match the reference's
typography, anchor and highlighting. Different rasterizers, codecs and video
processing still produce pixel differences.

- [Final generated MP4](../test_artifacts/caption-quality/after.mp4)
- [Before MP4](../test_artifacts/caption-quality/before.mp4)
- [Comparison at 2.4 seconds](../test_artifacts/caption-quality/comparison-2.4.png)
- [Comparison at 8 seconds](../test_artifacts/caption-quality/comparison-8.png)
- [Comparison at 14 seconds](../test_artifacts/caption-quality/comparison-14.png)
- [Measured transcription results](../test_artifacts/caption-quality/transcription-comparison.json)
- [Final editable render plan](../test_artifacts/caption-quality/after-plan.json)

## Changed files in this repair

New files:

- `backend/app/services/caption_layout.py`
- `backend/app/services/speech_models.py`
- `frontend/src/components/studio/useSpeechModels.ts`
- `frontend/src/components/studio/SpeechModelSelect.tsx`
- `tests/test_caption_quality.py`
- `tests/verify_caption_quality.py`
- `tests/verify_caption_transcription.py`
- `docs/caption-quality-repair.md`

Modified files, including files already uncommitted from the prior integration:

- `backend/app/services/caption_frames.py`: replaced `_paint` internals, active
  windows and raster cache version; removed the redundant token painter.
- `backend/app/services/caption_engine.py`: grouping, joined text and active windows.
- `backend/app/services/caption_fonts.py`: script runs.
- `backend/app/services/caption_documents.py`: ASS scale, color and positioning;
  removed heuristic emphasis scaling/capitalization.
- `backend/app/services/speech_transcription.py`: shared model service, validation,
  runtime status, Medium default, transcript cache version, emphasis behavior.
- `backend/app/services/auto_edit.py`: reference style, progress, model-aware reuse
  and preservation after failed/empty retranscription.
- `backend/app/schemas/editing_plan.py`: style defaults, active scale, model provenance.
- `backend/app/api/caption_routes.py`: model catalog/check endpoints.
- `backend/app/api/routes.py`: shared transcription default.
- `frontend/src/pages/StudioPage.tsx`: shared model selection/readiness, runtime
  messages, default style and stored model provenance.
- `frontend/src/components/studio/CaptionSettings.tsx`: reference style action,
  active-scale control, scaling guidance.
- `frontend/src/components/studio/CaptionTools.tsx`: clear model provenance on import.
- `frontend/src/types/index.ts`: style, model and runtime fields.
- `.env.example`, `backend/setup_local_assets.py`: recommended local model settings/help.
- `tests/test_caption_engine.py`, `tests/test_sections67.py`,
  `tests/test_creative_render.py`, `tests/test_caption_engine_browser.py`: relevant
  regression expectations, provenance/preservation and real Medium UI coverage.
- `docs/caption-engine-integration.md`: link to this current repair report.

No application dependencies were added or upgraded for this repair. The earlier
integration's Noto assets and notices are retained. Generated comparison media
remain under `test_artifacts/caption-quality`.

## Verification

| Check | Actual result |
| --- | --- |
| Selected Python unit/API/transcription/render regressions | 126 passed; two existing Pydantic fixture warnings |
| Quality and sections 6/7 tests rerun after failure-preservation safeguard | 30 passed (subset of the 126) |
| JavaScript caption/timeline suites | 13 passed |
| Targeted browser acceptance: real speech; native-script import/export; existing multitrack/caption and cinematic controls | All four passed across targeted runs |
| Final real-Medium generation/edit/regeneration/download/reload browser rerun after provenance changes | 1 passed in 92.41 s (included above) |
| Frontend production build, TypeScript and asset checks | Passed |
| Frontend lint | Exit 0; five existing warnings |
| Original-video Medium inference, raster comparison and MP4 decode | Completed |

Warnings remain in `CaptionTools.tsx`, `InteractiveTimeline.tsx` and
`StudioPage.tsx`; the Python serializer warnings are from existing transition
fixtures in `test_backend.py`. This is the selected regression suite, not every
optional external-service or model workflow.

Reproduce the broad backend checks from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_caption_quality.py tests/test_caption_engine.py tests/test_sections67.py tests/test_audit_regressions.py tests/test_creative_features.py tests/test_ai_editing.py tests/test_transcription.py tests/test_subtitles_export.py tests/test_creative_render.py tests/test_render_audit.py tests/test_backend.py -q --tb=short
node --test tests/test_caption_engine.mjs tests/test_subtitle_timeline.mjs tests/test_timeline_correctness.mjs
.\backend\.venv\Scripts\python.exe -m pytest tests/test_caption_engine_browser.py tests/test_studio_browser.py::test_multitrack_insert_caption_sound_controls_and_undo tests/test_studio_browser.py::test_cinematic_preset_and_manual_title_layout -q --tb=short
```

The browser suite uses installed Edge and Windows System.Speech. It starts and
stops isolated test servers; restricted environments may need permission to run
these local applications. The opt-in comparison scripts reference the supplied
local media paths. `verify_caption_transcription.py` reruns inference;
`verify_caption_quality.py --phase after --fresh` regenerates the after artifact.
The saved before artifact was captured before this repair; `--phase before` is
only an output label and does not restore old renderer code.

## Windows startup and use

From the Rayflow root, use the existing environment. Medium is already cached:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`. Restart an already-running backend/frontend to load
the changes. In Captions, wait for **Medium — cpu/int8**, then generate speech
captions. For existing tracks, use **Apply Caption Engine style** to apply the
reference typography. Review names and spoken text before export. The 9:16
comparison uses an explicit portrait export; choose 16:9 to retain this source's
landscape aspect ratio in Rayflow's existing export options.

Optional configuration values, added without replacing other `.env` entries:

```dotenv
WHISPER_MODEL=medium
WHISPER_DEVICE=auto
WHISPER_LOCAL_ONLY=true
```

For explicit CPU use, set `WHISPER_DEVICE=cpu` and
`WHISPER_COMPUTE_TYPE=int8`. To obtain another model once, when needed and online:

```powershell
.\backend\.venv\Scripts\python.exe backend/setup_local_assets.py --whisper small
```

Then choose **Check local models**. Substitute `medium`, `large-v3` or `turbo`
only when that model is wanted; disk cache and successful inference are both
required. The existing dependency/FFprobe installation instructions remain in
[the integration report](caption-engine-integration.md#windows-setup-and-run-commands).
Its old Tiny/Base defaults describe the earlier integration and are superseded here.

## Remaining limits

No selected check remains failing. Full multilingual coverage, multi-hour media,
real GPU inference and the uncached model sizes were not verified. RAQM and
appropriate fonts remain necessary for complex scripts; Arabic/Urdu and other
unbundled scripts are not guaranteed. Extreme manually entered text may need
shorter cues despite automatic fitting. Word alignment remains Whisper's estimate.

Caption Engine's optional paid speech adapters, diarization, prosody-driven
animations and clip-finding pipeline were not transplanted; the inspected sample's
basic phrase/active-word rendering is the target of this repair. Rayflow's existing
project storage and job lifetime behavior remain unchanged.

The separately reported Pixabay B-roll failure is not repaired by these caption
changes. Its previously identified URL-validation/cache issue remains separate.
