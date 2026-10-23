# Rayflow integration audit

Target: React 19 / TypeScript / Vite, FastAPI, local FFmpeg and faster-whisper.
Projects currently persist in browser localStorage; media persists under backend/storage.
The Prisma schema is aspirational, not an active NestJS/Next.js application.
Existing uncommitted caption, editor, and landing changes are preserved.

Reference: AI Video Production Editor, React/Electron with numerous provider-specific
services. Inspected src/App.tsx (splitWordsIntoSubtitleSegments),
src/utils/openTimelineIOExport.ts, src/utils/exportSettings.ts,
src/services/localLlmService.ts, src/workspaces/VideoGenerationWorkspace.tsx,
src/portal/pages/Analytics.tsx and services/dataService.ts.

Selected reuse: timed subtitle grouping (adapted to existing word timings and style)
and OpenTimelineIO interchange export (adapted to Rayflow's plan). Preserve upstream
GPL-3.0-or-later attribution and license. Retain Rayflow's existing local transcription,
Auto Reel, transitions, grading, preview, and FFmpeg rendering. Cloud generators need
different provider integrations and credentials; do not advertise them as implemented.
Reference analytics is a usage-record table, not portable render KPI calculations.

Confirmed issues:
- App mounts the landing immediately; Open Studio overlays the iframe's loader.
- VITE_API_URL in the example differs from VITE_API_BASE_URL in the client.
- Health requests have no deadline; no provider configuration/test interface exists.
- Ollama rejects configured remote servers; model substitution is silent, selection
  is not exposed, and a 12-second generation timeout hides errors behind fallback.
- Installed Ollama model is qwen3:8b; the sample model differs.
- Render/job data is in memory; historical analytics and restart recovery need storage.
- Production origins and storage paths need explicit configuration.

Eight phases: audit; initialization/settings; feature adapters; native navigation/UI;
measured analytics; Ollama transport/diagnostics; deployment; full verification.
Each phase includes targeted checks and an actual-results progress update.
