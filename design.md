# RayFlow AI Design

## Product direction

RayFlow AI is a focused cinematic reel workstation. It turns photographs, music, and natural-language direction into beat-synchronized vertical videos.

The product should feel like a calm creative tool rather than an automated content factory:

- **Clear**: every important action and processing state is understandable.
- **Cinematic**: the preview, typography, pacing, and motion should feel intentional.
- **Directable**: users can edit with controls, text commands, or voice.
- **Trustworthy**: the preview, timeline, and exported MP4 should represent the same edit.
- **Restrained**: use hierarchy, spacing, and typography instead of decoration.

## Experience architecture

The application has two primary surfaces:

1. **Landing page** — explains the product and gets a user into the studio.
2. **Studio** — provides the complete editing workflow.

### Landing page

The landing page introduces Rayflow AI through the existing Japanese night scene and section layout:

- Navigation with the Rayflow identity, existing section anchors, and **Open Studio**.
- Hero statement: “Your story. Your rhythm. Rayflow AI.”
- Supporting copy describing photos, video, beat synchronization, voice/text direction, and HD MP4 export.
- Primary **Open Studio** action and existing links for exploring the editing tools.
- Existing scene preview and large **RAYFLOW** banner, including the fallback wordmark.
- Five-step workflow: import footage, layer B-roll, shape color, direct the rhythm, and export.
- Existing feature sections explain beat sync, motion, color, titles, and captions; no additional sections are needed.

The landing page should stay concise. Its job is to establish confidence and move the user to the studio, not to reproduce the editor.

### Studio

The studio is organized as a three-part editing workspace:

- **Media and settings area**: photos, music, effects, style, title, captions, and inserts.
- **Central preview**: a true 9:16 composition with playback, seeking, audio state, and fullscreen controls.
- **Director and timeline area**: natural-language commands, assistant history, multi-track clips, beat markers, and edit history.

The studio must expose a clear path from import to export:

1. Add photos and reorder or remove them.
2. Add a soundtrack and inspect BPM/beat analysis.
3. Choose the aspect ratio, fit mode, pacing, motion, and transition style.
4. Add a title, captions, or inserts.
5. Direct the edit with text or voice.
6. Review the timeline and vertical preview.
7. Render and download the finished MP4.

### Captions and speech

Captions are part of the editing workflow rather than a separate post-processing step:

- Users can transcribe an uploaded soundtrack, select a supported language/model, and monitor transcription progress.
- Caption text, timing, style, position, and emphasis are editable before export.
- The preview uses the same caption layout and typography rules as the renderer so that captions remain aligned between review and the final MP4.
- Users can import or export caption documents in the supported text formats, including aspect-ratio-aware caption sizing.
- Romanized captions are available as an optional presentation layer without replacing the original transcript.
- Missing speech models, unsupported browser speech recognition, and transcription failures must be reported as recoverable states with the existing project preserved.

### Creative assistance

The director workflow may use local or configured providers for soundtrack analysis, natural-language edit interpretation, B-roll search, and cinematic previews. Provider availability must be visible when it affects an action; the editor must not report an edit as complete until the editing plan and timeline have been updated.

## Visual language

### Principles

- Use an ink-dark canvas with pale sage text, echoing the Japanese night scene on the landing page.
- Keep surfaces solid; do not introduce gradients into the application chrome.
- Use borders and spacing to define groups instead of heavy shadows.
- Use vermilion for primary actions and playback, brass for focus and AI tools, and jade for successful states.
- Keep the preview and media content visually dominant over the controls.
- Use line icons consistently; icons must have labels or accessible names when their meaning is not obvious.

### Color tokens

| Token | Value | Use |
| --- | --- | --- |
| Canvas | `#05070A` | Main page background |
| Surface | `#0D1417` | Studio panels and preview empty state |
| Raised surface | `#151F22` | Grouped settings and selected controls |
| Text | `#DFE7E0` | Primary headings and controls |
| Muted text | `#AEBDB3` | Descriptions and supporting labels |
| Subtle text | `#91A498` | Metadata, timestamps, and helper text |
| Border | `#3B4E50` | Cards, inputs, and timeline boundaries |
| Divider | `#263538` | Quiet separators between groups |
| Slider track | `#698476` | Sage rails with at least 3:1 contrast against Studio panels |
| Hover | `#223032` | Non-destructive hover surfaces |
| Vermilion | `#E0231C` | Primary actions and playback, with white text |
| Vermilion hover | `#B91F1B` | Primary action hover state |
| Brass | `#C9A66A` | Keyboard focus, AI tools, and warnings |
| Jade | `#9BB6AC` | Completed processing and healthy service state |
| Error | `#F4A498` | Failed uploads, analysis, rendering, or validation |

Success, warning, and error colors should be paired with text or an icon; color alone must not communicate state.

### Typography

- Use Onest with a system sans-serif fallback for the interface. Keep Japanese lettering as supporting detail alongside English navigation and editing copy.
- Use bold, tight tracking for hero and page headings.
- Use compact uppercase labels with increased tracking for metadata and section eyebrows.
- Use monospace text for technical values such as BPM, FPS, timestamps, and clip durations.
- Keep body copy at a readable line height and avoid long text inside dense editor controls.
- Cinematic title and caption typography is configured separately from the application chrome and must be previewed at the final 9:16 composition.

### Shape, spacing, and elevation

- Use `rounded-lg` for controls and compact cards.
- Use `rounded-xl` for larger panels and dialogs.
- Use `rounded-2xl` for the landing-page studio preview container.
- Prefer a 4px spacing rhythm, with 12px, 16px, 20px, and 24px as common panel intervals.
- Use only subtle shadows for floating or elevated surfaces; borders should carry most of the structure.
- Keep hit targets at least 40px where practical, and never make primary actions dependent on a tiny icon target.

## Component behavior

### Navigation

- Keep the product name visible while moving between the landing page and studio.
- The mobile navigation should collapse into a drawer.
- The back-to-home action in the studio must not discard the current local project.

### Buttons and controls

- Primary actions use a vermilion filled button with white text.
- Secondary actions use an ink surface with a muted sage border.
- Destructive actions require explicit danger styling and should not be adjacent to primary export actions without separation.
- Disabled controls must explain why they are unavailable when the reason is not obvious.
- Numeric inputs must support direct editing, clear bounds, and predictable increment/decrement behavior.

### Media

- Support drag-and-drop and batch selection for images.
- Show upload progress and validation errors close to the affected media.
- Make ordering explicit with a visible sequence and keyboard-accessible reorder controls.
- Preserve media state across refreshes through the existing local project persistence.

### Timeline

- Show clips on a horizontal time scale with visible duration, selection, and beat markers.
- Make clip selection distinct from playhead position.
- Keep trim and reorder operations reversible through undo and redo.
- Display the active time and total duration in a stable, readable position.
- Do not hide timing changes behind an assistant response; reflect them immediately in the timeline and preview.

### Assistant and voice direction

- The command composer should support text entry, microphone activation, submission, and clear error feedback.
- Conversation history distinguishes user directions from assistant confirmations.
- Assistant responses should describe the applied change, not claim an operation succeeded before the plan changes.
- Voice recording needs a visible listening state, a way to stop, and a usable fallback when browser speech recognition is unavailable.
- Example commands should teach the grammar without requiring the user to read documentation:
  - “Create a 20-second cinematic reel.”
  - “Sync the cuts to the beats.”
  - “Make the first photo last three seconds.”
  - “Add a title at the beginning.”

### Preview and export

- The preview is always framed at 9:16 unless the user explicitly selects another supported aspect ratio.
- Playback controls include play/pause, seek, current time, duration, audio mute, and fullscreen where supported.
- Preview loading, missing media, and render errors must be visible in the preview surface.
- Rendering is asynchronous. Show progress, allow the user to continue waiting without losing the edit, and provide a clear download action only when the job is complete.
- Export copy should state MP4 output at 30 FPS, with dimensions matching the selected format: 1080×1920 portrait, 1920×1080 landscape, or 1080×1080 square.

## Responsive behavior

### Desktop

- Use the full three-part studio layout.
- Keep the vertical preview centered and at a usable viewing size.
- Allow the timeline to scroll horizontally without moving the page unexpectedly.
- Keep the director controls close enough to the timeline to support rapid iteration.

### Tablet

- Reduce panel widths before reducing preview size.
- Allow the media/settings and director areas to become collapsible.
- Preserve the 9:16 preview and timeline as the primary editing surfaces.

### Mobile

- Use a single-column studio with the preview first, followed by contextual controls.
- Expose media and director panels through clearly labeled tabs or drawers.
- Keep the timeline horizontally scrollable and provide large enough handles for touch editing.
- Move secondary settings into collapsible sections; keep play, undo, redo, and export easy to reach.
- Do not require hover to discover essential actions.

## Accessibility

- Maintain visible keyboard focus for every interactive element.
- Use semantic headings and landmarks so the landing page and studio can be navigated by structure.
- Pair icons with accessible labels and provide text alternatives for status indicators.
- Keep text and controls at WCAG AA contrast or better against their surfaces.
- Announce upload, analysis, transcription, and render status changes to assistive technology.
- Respect reduced-motion preferences for preview transitions and interface animation.
- Ensure dialogs trap focus and return focus to the invoking control when closed.
- Never use color, position, or motion as the only indication of selection or status.

## Processing states

Every long-running operation should have explicit states:

| State | Required UI treatment |
| --- | --- |
| Ready | Action is available with a short explanation |
| Uploading | Progress indicator and affected file |
| Analyzing | Activity indicator, current operation, and cancel option where supported |
| Editing | Immediate plan/timeline update and assistant confirmation |
| Rendering | Progress, output details, and protection against accidental loss |
| Complete | Success message, preview/download action, and output metadata |
| Failed | Plain-language error, likely next step, and preserved project state |

Do not replace a failed operation with an empty or success-shaped result. Preserve the last valid plan and make recovery explicit.

## Content and tone

RayFlow copy is concise, confident, and specific:

- Prefer “Analyze soundtrack” over “Process audio”.
- Prefer “Render reel” over “Generate”.
- Explain technical values when they affect the result: BPM, aspect ratio, fit mode, duration, and frame rate.
- Avoid exaggerated claims about AI creativity or transcription accuracy.
- Use sentence case for actions and headings except where a cinematic title intentionally uses uppercase styling.

## Implementation references

The current implementation is organized around:

- [`frontend/src/pages/LandingPage.tsx`](frontend/src/pages/LandingPage.tsx) for the marketing surface, [`frontend/src/content/rayflowLandingCopy.json`](frontend/src/content/rayflowLandingCopy.json) for its copy, and [`frontend/scripts/brand-rayflow.mjs`](frontend/scripts/brand-rayflow.mjs) for generating the branded page while preserving the source layout.
- [`frontend/src/pages/StudioPage.tsx`](frontend/src/pages/StudioPage.tsx) for project state and the editing workflow.
- [`frontend/src/components/studio/`](frontend/src/components/studio/) for the timeline, creative controls, captions, effects, and preview.
- [`frontend/src/components/ui/`](frontend/src/components/ui/) for shared controls and navigation.
- [`frontend/src/types/index.ts`](frontend/src/types/index.ts) for shared editing-plan contracts.
- [`frontend/src/index.css`](frontend/src/index.css) for global typography and scrollbar behavior, and [`frontend/src/styles/theme.css`](frontend/src/styles/theme.css) for the shared Rayflow color tokens.
- [`frontend/src/utils/captionEngine/`](frontend/src/utils/captionEngine/) for caption layout, styling, and preview calculations.
- [`frontend/src/utils/romanizeCaptions.ts`](frontend/src/utils/romanizeCaptions.ts) for the optional Romanized caption layer.
- [`backend/app/api/caption_routes.py`](backend/app/api/caption_routes.py) and [`backend/app/services/caption_engine.py`](backend/app/services/caption_engine.py) for caption document handling, rendering contracts, and exports.
- [`backend/app/services/speech_transcription.py`](backend/app/services/speech_transcription.py) and [`backend/app/services/speech_models.py`](backend/app/services/speech_models.py) for transcription jobs and speech-model availability.
- [`backend/app/api/creative_routes.py`](backend/app/api/creative_routes.py) for provider-backed creative search, cinematic previews, and caption preview assets.

When adding a new studio feature, update the relevant type contract, editor surface, preview path, export path, persistence behavior, and failure state together.

## Design acceptance checklist

- The first-time user can understand the product and reach the studio from the landing page.
- A user can complete import, beat analysis, direction, preview, and export without losing project state.
- Every edit is reflected consistently in the plan, timeline, preview, and rendered output.
- Caption text and timing remain consistent across transcript editing, preview, caption export, and MP4 rendering.
- Speech-model and provider failures preserve the current project and provide a clear recovery path.
- Desktop, tablet, and mobile layouts retain access to the core workflow.
- Processing, cancellation, and failure states are explicit and recoverable.
- Keyboard, screen-reader, contrast, focus, and reduced-motion requirements are respected.
