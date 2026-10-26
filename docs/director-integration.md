# Director and provider integration

Implemented for Open Studio (`#/studio`), using the existing React 19/Vite application,
FastAPI service, workspace sessions, encrypted credential vault, shared reel persistence,
and `EditingPlan`. Node 24 and Python 3.10 were used for verification.

## Root causes

- The Director's Automatic path silently fell back to keyword parsing after provider
  errors. It supplied neither selection nor conversation to the previous planner.
- Caption timeline clicks only moved playback; no shared caption selection reached
  the editor keyboard handler. That handler only supported history shortcuts.
- Undo/redo callbacks read `planRef.current` after another statement had changed it,
  so redo could restore the wrong snapshot. History now captures values immediately.
- The instructional panel had no dismissal state. The existing “Try a direction”
  region is now the dismissible “Try AI Direction” panel.
- Partial changes already in the working tree had unconnected selection helpers and
  renamed Director imports with old call sites. Applying a response also submitted
  response-only fields to the now-strict action request schema.

## Provider configuration

First-time setup presents OpenAI and Anthropic cards. Each has a password input,
accessible show/hide toggle, model selector, Test connection, Save, and key removal
when configured. Save in setup activates that provider. Continue or Skip persists the
setup preference; subsequent loads of the workspace do not show setup again.
Connections exposes the same controls and a Director provider selector. The selector
waits for saved preferences before accepting changes, preventing an initial load from
overwriting a user's selection.

Verified official model IDs (2026-10-24):

| Provider | Model IDs | Official reference |
| --- | --- | --- |
| OpenAI | `gpt-6-astra`, `gpt-4.1` | [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1) |
| Anthropic | `claude-opus-5-5` | [Claude model catalog](https://platform.claude.com/docs/en/models/overview) |

Connection testing retrieves the selected model from the official provider API.
It verifies authentication and model access, not remaining generation quota. Draft
key tests do not save the key. Missing keys, forbidden access, unavailable models,
rate limits, timeouts, malformed responses, and network failures have redacted errors.
Model availability is account-dependent; catalog entries are not a claim of access.

Keys are entered in the browser and submitted only to the app's authenticated,
write-only backend endpoint. This one submission is necessarily visible to the person
entering it in their browser's developer tools. Keys are never put in frontend code,
browser storage, URLs, or browser-to-provider requests, and are never returned by the
backend. Existing AES-GCM encryption binds stored keys to the workspace and provider.
Origin checks and session ownership protect credential routes; validation responses
omit rejected inputs so malformed submissions cannot echo secrets. The current
deployment is a web application, including local development, not a native desktop app.

## Editing behavior

`instruction → selected provider → typed action plan → validation and review →
deterministic commands → existing state/history → preview and autosave`.

The model gets the current plan (clip metadata, media references, captions,
transcript, overlays), selected clip/caption IDs, playhead, available history, and
the last 20 conversation messages. Clarifications and unsupported requests return
without executing anything. Existing explicitly selected Local commands and Ollama
remain available; Automatic has no silent keyword fallback.

Supported registry actions:

- `remove_subtitles`, `generate_subtitles` (restore from retained transcript),
  `style_subtitles`, and `add_subtitles` with supplied text and validated timings.
- `add_title`, `remove_title`, `set_aspect_ratio`, `add_transition`, `set_clip_volume`.
- `split_clip`, `trim_clip`, `move_clip`, `delete_clip`, `shorten_video`.
- `remove_silence`: analyzes owned source audio, retaining margins around measured
  silence and producing source-relative clip ranges.
- `undo`, `redo`: execute against Studio's actual history.

Each batch edits a deep copy and publishes only after all operations validate. Clip
edits retime attached captions, transcripts, inserts, titles, and sounds. Splits
preserve attachments across both pieces. Removed captions retain their latest text
and style for follow-ups such as “keep them, but make them smaller.” Each batch is
one undo entry. The client refuses stale responses if the active plan changed during
planning, review, or execution. Completion messages come from executed commands.

Captions share one selection between the timeline, raster preview hit regions, and
caption list. Preview hit regions use the actual rendered alpha bounds. Delete and
Backspace prioritize caption selection, then selected audio or clip. Text inputs,
textareas, nested contenteditable regions, selectors, dialogs, IME composition,
already-handled events, repeat deletion, and unrelated focused UI are excluded.
Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z, and Ctrl/Cmd+Y use the same history. Audio deletion now
also restores audio and analysis on undo. Caption-list trash buttons remain available.

The instructional close button has an accessible name and uses React state plus
sessionStorage. Dismissal survives rerenders and navigation in the tab; conversation,
voice input, and text input remain available. The Director accepts multiline input,
shows planning/application status, displays readable summaries, and links errors to
Connections.

## Changed files

Paths are relative to the repository root. This includes completed pre-existing
partial changes; the unrelated `scripts/diagnose_agentrouter_stream.ps1` was preserved.

| File | Purpose |
| --- | --- |
| `backend/app/services/ai_provider.py` | Shared official provider transport, verified catalog, redacted errors and connection tests. |
| `backend/app/editor/providers.py` | OpenAI/Anthropic catalog and encrypted credential lifecycle integration. |
| `backend/app/services/provider_settings.py` | Selected provider resolution and workspace-scoped model/key lookup. |
| `backend/app/api/editor_routes.py` | Test draft or saved provider configuration. |
| `backend/app/main.py` | Omit secret-bearing inputs from validation responses. |
| `backend/app/schemas/editing_actions.py` | Shared action parameter registry and validation. |
| `backend/app/schemas/ai_editing.py` | Director requests, context, conversation, and valid action sequences. |
| `backend/app/services/ai_editing.py` | Contextual planning, deterministic actions, restoration and transactional execution. |
| `backend/app/services/director_silence.py` | Measured silence removal and split attachment preservation. |
| `backend/app/services/timeline_edits.py` | Bound and retime attached and global overlays after clip edits. |
| `backend/app/api/routes.py` | Forward context and conversation to the planner. |
| `backend/app/services/caption_frames.py` | Optional normalized preview hit regions from caption raster bounds. |
| `backend/app/api/creative_routes.py` | Return caption hit regions with preview frames. |
| `frontend/src/App.tsx` | Suppress startup setup for configured workspaces. |
| `frontend/src/components/WorkspaceSetup.tsx` | Explain optional conversational provider setup. |
| `frontend/src/components/ProviderConnections.tsx` | Password visibility, verified model selectors, draft testing and provider saving. |
| `frontend/src/pages/SettingsPage.tsx` | Provider switching and safe loading of saved preferences. |
| `frontend/src/services/editorClient.ts` | Typed provider model catalog. |
| `frontend/src/services/settings.ts` | Provider status/preferences and change notifications. |
| `frontend/src/services/api.ts` | Shared Director requests with context and response-only field exclusion on apply. |
| `frontend/src/types/index.ts` | Extended Director action/context contracts. |
| `frontend/src/utils/editorSelection.ts` | Text-focus guard and immutable caption deletion/restoration data. |
| `frontend/src/pages/StudioPage.tsx` | Real Director execution/history, caption selection, shortcuts, stale-plan guards, status and tips dismissal. |
| `frontend/src/components/studio/InteractiveTimeline.tsx` | Caption/audio/clip selection and keyboard accessibility. |
| `frontend/src/components/studio/useCreativePreview.ts` | Expose actual caption hit regions and invalidate stale preview captions. |
| `tests/test_director_integration.py` | Provider isolation, errors, context, action validation, atomicity, restoration, retiming and silence analysis. |
| `tests/test_director_browser.py` | Chrome setup, selection, shortcuts, undo/redo, real apply, persistence, stale responses, mobile dismissal and missing-provider flows. |
| `tests/test_audit_regressions.py` | Use the workspace session now required for media reads. |
| `tests/test_e2e_workflow.py` | Use uploaded media references for the existing full render/download workflow. |
| `README.md` | Replace obsolete automatic keyword-fallback documentation. |
| `docs/director-integration.md` | Implementation, files, verification and operational limitations. |

## Executed verification

| Check | Actual result |
| --- | --- |
| `npm.cmd run build` | Passed, exit 0. TypeScript and production bundling completed; large-chunk and mixed static/dynamic import warnings remain. |
| `npm.cmd run lint` | Exit 0: 465 warnings, zero errors. |
| `npm.cmd test` | 16 passed. |
| `npm.cmd run test:editor` | 171 passed. |
| Full non-browser Python suite: `pytest tests --ignore-glob='*browser*'` | 295 passed, 2 failed initially. Both failures used obsolete media access patterns in older fixtures. |
| Rerun `test_audit_regressions.py` and `test_e2e_workflow.py` after fixture corrections | All 7 passed, including real FFmpeg rendering and MP4 download. |
| Final targeted Python run: Director, AI editing, caption engine/quality, editor integration | All 103 passed. |
| Five new Chrome scenarios against the production bundle | All 5 passed. |
| Expanded Chrome caption/history and Director scenarios | Both passed, including nested contenteditable, numeric inputs, and conversational undo/redo. |
| Existing `test_shared_studio_browser.py` | Passed: upload, Auto Reel, caption import, preview, saving/navigation, real FFmpeg export and MP4 download. |
| `git diff --check` | Passed. |

The full Python suite was not repeated after its two fixture corrections; the failed
test modules and affected Director/caption integration suites were rerun as recorded
above. Browser checks used `tests/run_browser_checks.py`, private test workspaces,
headless Chrome, and isolated service ports. An intermediate diagnostic dev-server
run lost its service connection; final acceptance uses the production bundle.

Logs are in ignored `test_artifacts/`, particularly `director-build-verified.log`,
`director-lint-verified.log`, `director-regression.log`,
`director-regression-recheck.log`, `director-final-unit.log`,
`director-browser-verified.log`, and `director-browser-history.log`.
Browser trace ZIPs and service logs are inside the corresponding `browser-*` folders.
Provider mocks test routing, errors, schemas, and execution; they do not measure live
model understanding of equivalent wording. No live-provider success is claimed.

## Deployment and practical limits

- Follow [hosted deployment](hosted-editor-deployment.md): HTTPS, same-origin `/api`
  proxy, approved origins, private storage, and a stable backend-only
  `RAYFLOW_VAULT_SECRET` of at least 32 characters. Never configure provider keys as
  `VITE_*` variables. No real keys were added to the repository.
- Live paid inference was not run. Automated provider responses are mocked; the
  command executor, storage, browser editor, caption rasterization, and FFmpeg checks
  are real. Use Test connection with your own credentials, then verify a short edit.
- New speech needs the existing local Captions transcription workflow and a ready
  speech model. The Director restores retained transcript captions; it cannot
  fabricate a missing transcript.
- “Keep important moments” depends on transcript/context. Without enough evidence
  the model must ask what to retain. `shorten_video` proportionally trims every clip;
  it does not claim to identify highlights.
- Silence analysis supports video sources up to 30 minutes and at most 24 silence
  cuts per action, with conservative speech margins. It does not detect importance.
- History is the existing in-memory Studio history. Undo/redo must be separate
  requests from other actions. Restoring removed captions and restyling them can run
  in one batch. Conversation resets on project load; recent messages persist within
  the active Studio conversation.
- No hosting deployment was performed. Existing guest-session expiry behavior is
  unchanged; workspace/account access controls still apply.
