# Selected reference integrations

Original project: AI Video Production Editor by Ludwig Maximillian Kienle,
https://github.com/LudwigKienle/ai-video-production-editor (GPL-3.0-or-later).
The selected code and adaptations retain NOTICE and LICENSE under
frontend/src/vendor/aivpe. Distribution of this derivative must comply with that
license, including corresponding source obligations. Rayflow is not the official
upstream application.

| Reference implementation | Rayflow integration | Behavior |
| --- | --- | --- |
| src/App.tsx: splitWordsIntoSubtitleSegments | utils/smartCaptions.ts; CaptionTools | Split measured words at punctuation, pauses, length and duration limits. Preserve style and word metadata; clamp to existing caption bounds. Short-tail merge cannot exceed limits. |
| src/utils/openTimelineIOExport.ts: buildOpenTimelineIOFromTimeline and helpers | vendor/aivpe; utils/timelineExport.ts; studio toolbar | Preserve the original gap, track, trim and reference serialization. Map Rayflow clips and soundtrack into the narrow upstream input types. |
| src/services/localLlmService.ts: probeLocalServer/listLocalModels | Backend Ollama client and Connections | Adopt discovery and explicit model selection behavior; retain backend transport rather than Electron/browser networking. |
| src/portal/pages/Analytics.tsx | Dashboard | Reference displays usage records; Rayflow calculates metrics from its own processing lifecycle instead. No reusable render KPI calculation exists there. |

Existing faster-whisper timing, multilingual caption rendering, transcript import,
SRT/VTT/ASS/JSON downloads, speech tightening, Auto Reel, motion, grading, transitions,
undo/redo, and MP4 export are retained. Auto Reel builds from uploaded media; it does
not synthesize new footage. Cloud video/voice generation was not copied because it
requires separate providers, SDKs, credentials and a different orchestration system.

OTIO is an interchange file, not a rendered video. Media must remain reachable or be
relinked in the destination editor. Rayflow effects are kept in metadata, not claimed
to render in third-party editors. MP4 is the visual final export.
