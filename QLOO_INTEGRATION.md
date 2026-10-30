# RayFlow AI — Qloo Taste AI Integration

RayFlow AI is a **video editing** studio that now understands your taste. This
document describes how Qloo's cultural intelligence is integrated to personalize
editing decisions, while preserving the existing editing engine.

> RayFlow edits video. Qloo understands taste. The agent interprets taste.
> RayFlow executes supported editing operations. The output is always an
> **editable timeline** — never a black-box generated video.

## Contents
- [Architecture](#architecture)
- [Qloo API usage](#qloo-api-usage)
- [Taste profile](#taste-profile)
- [Taste Intelligence agent](#taste-intelligence-agent)
- [Product integration](#product-integration)
- [Backend API](#backend-api)
- [Configuration](#configuration)
- [Privacy](#privacy)
- [Testing](#testing)

## Architecture

```
Declared preferences (user)
        │  (names/genres only — never media)
        ▼
Qloo /search  +  /v2/tags   → entity IDs, tag IDs
        ▼
Qloo /v2/insights           → cultural associations + tag signals
        ▼
Taste Profile (normalized, persisted per workspace)
        ▼
Taste Intelligence agent (LLM or rule-based) → validated editing strategy
        ▼
RayFlow editing engine (Auto Reel / AI Director) → EDITABLE timeline
        ▼
Existing FFmpeg renderer → MP4
```

Backend modules (`backend/app/services/qloo/`):

| File | Responsibility |
| --- | --- |
| `client.py` | Secure HTTP transport: `X-Api-Key` header, timeouts, retries (429/5xx), error mapping. Never leaks the key or upstream bodies. |
| `entity_resolver.py` | Resolve declared preferences to Qloo entity IDs (`/search`) or tag IDs (`/v2/tags`). Reports unresolved items. |
| `taste_analyzer.py` | Retrieve cultural intelligence from `/v2/insights` using entities/tags as signals; aggregate associations + tag signals. |
| `profile_builder.py` | Assemble a normalized `TasteProfile` keeping declared / resolved / Qloo-derived layers distinct. |
| `cache.py` | Private in-process TTL + LRU cache of Qloo responses (permitted by Qloo terms; never persisted publicly). |
| `schemas.py` | Internal normalized schemas with source-entity references for auditability. |

Agent + engine glue:

| File | Responsibility |
| --- | --- |
| `services/taste_intelligence.py` | Feeds the profile to the existing AI provider (`generate_plan`) and validates the output into a `TasteEditingStrategy`. Falls back to a deterministic rule engine with no key. |
| `services/taste_reel.py` | Overlays a strategy onto the existing Auto Reel engine to produce an editable plan. |
| `schemas/taste.py` | `TasteEditingStrategy` — every field constrained to values the renderer supports. |
| `api/taste_routes.py` | FastAPI routes (workspace-scoped). |

## Qloo API usage

Per the [Qloo hackathon guide](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide):

- **Base URL:** `https://hackathon.api.qloo.com` (hackathon keys only work here).
- **Auth:** `X-Api-Key: <key>` header (not a query param, not a bearer token).
- **Endpoints used:** `GET /search`, `GET /v2/insights`, `GET /v2/tags`.
- **Never used:** `/recommendations`, `/recs` (legacy, unsupported).
- `/v2/insights` is a **GET** with query-string params; every request includes
  `filter.type` (e.g. `urn:entity:movie`, `urn:entity:artist`).
- Signals: `signal.interests.entities`, `signal.interests.tags`.
- Handling: a `403` means the entity type is not permitted (skipped, not fatal);
  an empty `results` array is a valid "no data" outcome; `429`/`5xx` are retried
  with capped backoff honoring `Retry-After`.

All Qloo requests are **server-side only**. The key is read via
`setting('QLOO_API_KEY')` and is never sent to the browser.

## Taste profile

The **Discover Your Taste** page (`#/taste`) lets a user enter favorite movies,
directors, artists, genres, moods, and aesthetic styles using only
Qloo-supported categories. The backend resolves them, retrieves insights, and
builds a profile with three clearly separated layers, surfaced in the UI as:

- **YOU SAID** — declared preferences (never inferred).
- **QLOO INFERRED** — resolved entities + Qloo-derived cultural associations and
  tag signals (clearly labeled as inferred, with affinity scores).
- **AI DECIDED** — the editing interpretation (strategy), shown with reasoning.

Profiles are persisted per workspace in the existing record store
(`store` collection `taste_profiles`), with full workspace isolation.

## Taste Intelligence agent

`generate_strategy(profile_summary, allow_llm)`:

1. Builds a prompt containing **only** the declared preferences and real Qloo
   signals (names, types, tags, affinities — no media).
2. Calls the existing AI provider abstraction (`generate_plan(messages)`), reusing
   whatever provider the user connected (Gemini/OpenAI/Anthropic/OpenRouter/
   Agent Router/Ollama).
3. Validates the response against `TasteEditingStrategy` (Pydantic). Invalid
   output is rejected and the agent falls back to the rule engine.
4. With no AI key, a deterministic rule engine maps Qloo tag/association
   keywords onto a supported strategy — so the feature works without any key.

The LLM is explicitly instructed to reason only from supplied Qloo data and
never invent cultural associations. The strategy only ever contains values the
renderer supports, so the agent can never emit an arbitrary/unsafe operation.

## Product integration

- **Auto Reel** gains **“Create a Reel Based on My Taste”** in Studio. It builds
  a strategy from the saved profile and runs the existing Auto Reel engine with
  the strategy overlaid (pacing, color mood, motion, transitions, beat sync).
  The result is a normal, fully editable timeline.
- **AI Director** is taste-aware: the backend injects the saved profile summary
  into the editor context for `/api/ai/plan` (server-side, not spoofable). For
  subjective requests like “make it more cinematic”, the Director uses the taste
  signals and cites them. The existing **review-and-approve** flow is preserved;
  nothing is applied without user approval.
- **Music/pacing**: Librosa still performs all real audio analysis and beat
  detection. Qloo only informs *preferences* (music direction, beat density
  intent). Qloo never analyzes uploaded audio.

## Backend API

All routes are workspace-scoped and require a session.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/taste/profile` | Fetch the saved profile + summary. |
| `POST` | `/api/taste/profile` | Build and save a profile from preferences. |
| `PUT` | `/api/taste/profile` | Update the saved profile. |
| `POST` | `/api/taste/analyze` | Resolve + analyze without persisting (preview). |
| `POST` | `/api/taste/edit-plan` | Generate a validated taste editing strategy. |
| `POST` | `/api/taste/apply` | Return a taste-adjusted plan for review (not auto-applied). |
| `POST` | `/api/taste/reel/jobs` | Start an async “reel based on my taste” job. |

Validation (Pydantic), structured responses, workspace isolation, per-workspace
rate limiting, and origin checks follow the existing conventions.

## Configuration

Local development — add to `backend/.env`:

```dotenv
QLOO_API_KEY=your_hackathon_key
# optional override (defaults to the hackathon host)
QLOO_BASE_URL=https://hackathon.api.qloo.com
```

Production (Cloud Run) — stored in Secret Manager and injected as env; see
`GCP_CLOUD_RUN_DEPLOYMENT.md`. `QLOO_API_KEY` is a shared backend credential
(not per-user) and falls back to the process environment.

Without a key, the Taste Profile builds a **declared-only** profile and the rule
engine still produces a strategy — manual editing and Studio export never
require Qloo or an LLM key.

## Privacy

- **Uploaded photos, videos, and audio are never sent to Qloo.** Only the
  cultural preference text (and derived entity/tag IDs) are sent.
- The Qloo key stays on the backend; it is not exposed in frontend code or the
  built bundle.
- Qloo responses are cached only in process memory, never written to a public
  location.

## Testing

- `tests/test_qloo_client.py` — client transport with mocked HTTP (auth header,
  retries, 401/403/429 handling, empty results, response-shape normalization).
- `tests/test_taste_intelligence.py` — entity/tag resolution, profile layering,
  rule-based strategy differentiation, schema validation, LLM fallback, strategy
  application to a plan.
- `tests/test_taste_routes.py` — full FastAPI flow with mocked Qloo (session,
  persistence, declared-only vs Qloo-backed, approval flow, context injection).
- `tests/test_qloo_live_integration.py` — **real** Qloo calls, skipped unless
  `QLOO_API_KEY` is set. A mocked test is never reported as a live pass.

Run:

```bash
# offline (mocked) — no key needed
backend/venv/Scripts/python -m pytest tests/test_qloo_client.py tests/test_taste_intelligence.py tests/test_taste_routes.py

# live integration — requires a real key
QLOO_API_KEY=your_key backend/venv/Scripts/python -m pytest tests/test_qloo_live_integration.py -v
```
