**Rayflow AI editor layout and opening experience**

**Root cause.** The reproducible blank-space bug was `AIAssistant.tsx` calling `messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })`. That scrolled ancestor containers, including the editor frame with `overflow: hidden`. After resizing from 1440×1000 to 1366×768, the frame body began at y=-154 instead of y=111: a 265px displacement, leaving the workspace bottom at y=503 and black space below. The initial desktop dimensions alone did not reproduce the bug; resizing exposed it. The clip strip in `EditorPageShell.tsx` used the same ancestor-scrolling API.

The layout also had conflicting viewport ownership: the shell only had `min-h-screen`; the editor subtracted 58px, 96px, then 74px at different breakpoints and forced minimum heights of 560px, 520px, then 640px. At 844×390 the editor extended to y=618. Side-panel inline `minWidth: 0` defeated their CSS minimum, squeezing the media browser. Preview and timeline percentage flex bases consumed 100% of the center before its toolbar, dividers and gaps were counted. Mobile bottom navigation had a centered intrinsic-width grid with no horizontal scrolling.

**Layout fix.** The application shell now owns the viewport with `auto minmax(0, 1fr)` rows. The editor inherits the remainder beneath the actual, potentially wrapped navigation. Main-content grid sizing, zero minimums on flexible containers and independent panel/track scrolling maintain that chain. The center uses grid rows for toolbar, preview, divider and timeline; fractional sizes apply to remaining space with usable monitor/track minimums. Short screens can scroll the center without collapsing controls. Narrow screens use the existing Media/Timeline/Inspector tabs. The chat and clip strip scroll their own containers; the outer frame cannot scroll. Transport and bottom navigation controls scroll horizontally when necessary. Divider movement now uses incremental mouse deltas and the correct direction.

**Smaller starting window.** The API-provider setup, onboarding and settings dialogs use a 48rem maximum width instead of the shared 1080px width, an 80dvh height limit, a scrolling content body, and stationary actions. All provider fields, model lookup, save/test/remove controls and skip/continue options remain available.

**Emoji cleanup.** UI icons now use the already-installed `lucide-react`, with consistent 16px size and 1.75 stroke width for replacements. This covers assistant actions/modes, production categories, moodboards, scene maps, Director Mode, analysis, suggestions, favorites, status checks and the Studio close control. Decorative model-badge emojis were removed while preserving badge labels. Existing saved category icons map to SVGs without changing saved project documents. Keyboard notation and user-authored content are retained. A scan of TS, TSX and CSS under `frontend/src` found no remaining pictographic UI characters in the checked Unicode ranges.

**Loading experience.** The mark SVG, preloader typography and progress-line styles were extracted from the actual Kage landing preloader into shared public assets; the branding generator applies those assets to the landing page too. Its scene animation/readiness lifecycle remains intact. `WorkspaceLoading` covers session startup, lazy editor-module loading, project hydration, preview startup and errors. Project hydration restores media records, tracks, clips and waveform state before rendering the editor. Opening finishes after the first frame's required image/video/audio media decodes, fonts are ready and the canvas draws. There is no artificial success delay. Metadata requests and preview initialization have failure deadlines. Retry reattempts project loading or just remounts the preview, retaining the restored document. Panel changes do not restart loading. A short opacity transition respects reduced-motion preferences.

**Changed files.** Paths are relative to the repository. Existing user changes in the working tree were preserved.

| File | Reason |
| --- | --- |
| `frontend/src/App.tsx` | Viewport-owning editor shell and branded startup/Suspense fallback. |
| `frontend/src/components/WorkspaceLoading.tsx` | Shared loading and retry presentation. |
| `frontend/src/components/WorkspaceSetup.tsx` | Compact API-key setup with scrollable body and fixed actions. |
| `frontend/src/components/ModuleBoundary.tsx` | Branded module-load error and retry. |
| `frontend/src/styles/workspace.css` | Shell grid and compact dialog sizing. |
| `frontend/src/index.css` | Load shared preloader styles. |
| `frontend/src/pages/StudioPage.tsx` | Replace the Auto Reel close glyph with Lucide X. |
| `frontend/src/services/editorClient.ts` | Bound metadata requests; preserve caller signals and large-upload lifetime. |
| `frontend/src/features/ai-editor/App.tsx` | Integrate readiness and retry into existing project initialization; keep the workspace mounted during subsequent project loads. |
| `frontend/src/features/ai-editor/EditorWorkspace.tsx` | Branded render-error fallback. |
| `frontend/src/features/ai-editor/upstream.css` | Structural grid, scrolling, panel minimums, transport and navigation sizing. |
| `frontend/src/features/ai-editor/editor.css` | Regenerated scoped editor stylesheet from upstream source. |
| `frontend/src/features/ai-editor/rayflow.css` | Remove conflicting viewport calculations and extend existing responsive panel tabs. |
| `frontend/src/features/ai-editor/landing.css` | Replace decorative check character with an SVG mask. |
| `frontend/src/features/ai-editor/components/AIAssistant.tsx` | Confine message scrolling; replace assistant emojis with SVGs or descriptive status text. |
| `frontend/src/features/ai-editor/components/ApiKeyModal.tsx` | Compact settings dialog and scrollable body. |
| `frontend/src/features/ai-editor/components/OnboardingModal.tsx` | Compact onboarding and stationary footer. |
| `frontend/src/features/ai-editor/components/PreviewPlayer.tsx` | Signal first-frame readiness/errors and retain space for playback controls. |
| `frontend/src/features/ai-editor/components/EditorPageShell.tsx` | Scroll only the clip strip when selection changes. |
| `frontend/src/features/ai-editor/components/StudioIcon.tsx` | Shared Lucide rendering and legacy category-icon compatibility. |
| `frontend/src/features/ai-editor/components/ExtraAssetsSection.tsx` | SVG asset-category icons. |
| `frontend/src/features/ai-editor/components/Header.tsx` | SVG selected-profile check. |
| `frontend/src/features/ai-editor/components/DesignSystemSheet.tsx` | SVG sample star button. |
| `frontend/src/features/ai-editor/workspaces/EditWorkspace.tsx` | Center grid, preview readiness callbacks and corrected resizing. |
| `frontend/src/features/ai-editor/workspaces/MoodboardWorkspace.tsx` | SVG category/tool/lock icons and an icon selector. |
| `frontend/src/features/ai-editor/workspaces/SceneMapWorkspace.tsx` | SVG palette and scene-element icons. |
| `frontend/src/features/ai-editor/workspaces/ImageGenerationWorkspace.tsx` | SVG Director Mode, camera, lighting, generation and favorite icons. |
| `frontend/src/features/ai-editor/workspaces/AnalysisWorkspace.tsx` | SVG analysis and loaded-context indicators. |
| `frontend/src/features/ai-editor/workspaces/MicrodramaWorkspace.tsx` | SVG preset icons. |
| `frontend/src/features/ai-editor/workspaces/ProjectHubWorkspace.tsx` | Remove badge emojis; SVG status/suggestion indicators. |
| `frontend/src/features/ai-editor/workspaces/PluginsWorkspace.tsx` | Preserve star counts as explicit text. |
| `frontend/src/features/ai-editor/workspaces/VideoGenerationWorkspace.tsx` | Remove emoji from the native Auto option. |
| `frontend/src/features/ai-editor/data/extraAssetTypes.ts` | Semantic icon names for asset categories. |
| `frontend/src/features/ai-editor/data/sceneMapTypes.ts` | Semantic icon names for scene templates. |
| `frontend/src/features/ai-editor/data/moodboardTypes.ts` | Semantic icon names for default moodboard categories. |
| `frontend/src/features/ai-editor/config/uiModes.ts` | Replace emoji metadata with semantic icon names. |
| `frontend/src/features/ai-editor/services/falVideoCatalog.ts` | Preserve Cheap badge text without emoji. |
| `frontend/src/features/ai-editor/services/higgsfieldService.ts` | Preserve Cinematic badge text without emoji. |
| `frontend/scripts/brand-rayflow.mjs` | Reuse shared preloader assets in generated landing HTML. |
| `frontend/public/landing-pages/kage.html` | Regenerated branded landing page using shared preloader assets. |
| `frontend/public/landing-pages/rayflow-mark.svg` | Extracted landing preloader mark. |
| `frontend/public/landing-pages/rayflow-preloader.css` | Shared landing/editor preloader styles and reduced-motion transition. |
| `tests/test_editor_layout_browser.py` | Layout, scrolling, dialogs, initialization/retry, resizing, media playback and restoration regressions. |
| `docs/editor-layout-verification.md` | This report and verification record. |

Diagnostic scripts, screenshots, isolated service storage and logs were written beneath ignored `test_artifacts/`; no user project or provider credentials were used for browser tests.

**Verification.** The app was built and opened in headless Chrome against real, isolated Uvicorn and Vite production-preview servers. The test runner shut those servers down afterward.

| Executed command | Actual result |
| --- | --- |
| `cd frontend; npm.cmd run build` | Passed, including branding/source-asset checks, CSS generation, TypeScript build and Vite production build. Bundle-size and ineffective-dynamic-import warnings remain. |
| `cd frontend; npm.cmd run lint` | Exit 0: no errors, 465 warnings across the current codebase. |
| `cd frontend; npm.cmd run test:editor` | 171 passed. |
| `cd frontend; npm.cmd test` | 16 passed. |
| `backend/venv/Scripts/python.exe tests/run_browser_checks.py tests/test_editor_layout_browser.py tests/test_editor_browser.py tests/test_editor_workspaces_browser.py tests/test_editor_export_browser.py tests/test_editor_grading_browser.py` | 9 passed; the newly added video/audio test hit an ambiguous test selector when two uploaded assets were present. The selector was corrected. All six existing browser cases in this run passed. |
| `backend/venv/Scripts/python.exe tests/run_browser_checks.py tests/test_editor_layout_browser.py` | 4 passed after the selector correction, on the final application build. |
| `backend/venv/Scripts/python.exe tests/run_browser_checks.py tests/test_editor_layout_browser.py -k video_audio` | 1 passed, 3 deselected, with additional canvas-pixel assertions proving decoded video playback before and after restoration. |
| Unicode/escaped-character scan of frontend TS/TSX/CSS and landing HTML | No remaining UI emoji matches. |
| `git diff --check` for changed tracked sources | No whitespace errors. |

Ten distinct browser cases passed across these runs. An earlier Scene Wall navigation timeout passed both an isolated diagnostic rerun and the broader verification run; its initial intermittent cause was not established. The initial attempt to use `backend/.venv` could not start the server because that environment lacked `cryptography`; the existing `backend/venv` successfully ran all subsequent browser checks. PowerShell blocked `npm.ps1`, so verification used `npm.cmd`.

Routes tested: `/#/editor`, `/#/studio`, `/#/dashboard`, `/#/connections`, and the landing page at `/#/`. Editor workspaces exercised include Timeline, Media, Inspector, Design, Nodes, Moodboard, Project, Scene Wall, Color and Deliver.

Layout assertions and screenshots cover 1440×1000, 1366×768, 1024×768, 390×844, 844×390 and 1920×1080. Functional suites also use 1600×1000, 1600×1100 and 1700×1100. At every layout size the editor bottom equals the viewport bottom, its top follows the measured navigation height, its frame scroll position remains zero, and the document has no horizontal overflow. Short-screen timeline controls and both ends of the mobile bottom navigation are reachable by independent scrolling. Divider movement, side-panel tabs, setup fields/footer, project failure/retry and missing-preview-media retry passed.

Functional checks exercised uploads, video drag-and-drop, audio insertion, playback advancement, saved-media restoration, undo/redo, shared assets, project save/navigation, design/moodboard persistence, API-key storage isolation, landing return/reentry, HQ FFmpeg export, browser WebM export, cancellation, LUT import and rendered grading colors. External paid AI generation services were not called.

Evidence is retained in `test_artifacts/layout-build-verified.log`, `layout-lint-final.log`, `layout-editor-tests.log`, `layout-app-tests.log`, `layout-browser-final.log`, `layout-browser-confirmed.log`, and `layout-playback-confirmed.log`. Baseline screenshots and geometry are in `test_artifacts/browser-a1748b03c1ec4399bfe1f748cc8d9120/pytest/test_inspect_layout0/`. Final layout measurements/screenshots are in `test_artifacts/browser-6d439e52f74244ea8c3ec3f4b1123ed5/pytest/test_editor_layout_and_compact0/`. Export and grading artifacts are in `test_artifacts/browser-05f8b91e1e3f4600a993c9181e58e22a/pytest/`. The decoded-video restoration screenshot is in `test_artifacts/browser-03d7b7859ed64353b464928c12b8042e/pytest/test_video_audio_playback_and_0/video-audio-restored.png`.

**Remaining limitations.** Lint warnings and large production chunks remain. Live provider generation and non-Chrome browsers were not verified. No unresolved reproducible layout, loading, media-playback or export failure was found in the executed checks; the earlier intermittent Scene Wall timeout remains noted above.
