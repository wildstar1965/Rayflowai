# RayFlow AI — Voice-Controlled Cinematic Reel Studio

RayFlow AI is a production-quality creative workstation that transforms photographs, audio soundtracks, and natural-language voice directions into beat-synchronized vertical cinematic reels (1080×1920 MP4).

Inspired by Apple's clean, restrained product design and Notion's organized workspace layout, RayFlow AI pairs an intuitive multi-track editing timeline with an intelligent audio-visual compositor powered by Python, Librosa, and FFmpeg.

---

## Architecture & System Overview

RayFlow AI follows a high-performance modular architecture:

```
Rayflow.ai/
├── frontend/                     # React 19 + TypeScript + Vite + Tailwind CSS
│   ├── src/
│   │   ├── components/
│   │   │   └── ui/               # Clean, accessible monochrome UI components
│   │   │       ├── Button.tsx    # Apple-style restrained buttons
│   │   │       └── Navbar.tsx    # Reliable, responsive navbar with mobile drawer
│   │   ├── pages/
│   │   │   ├── LandingPage.tsx   # Minimalist, typography-driven product landing page
│   │   │   └── StudioPage.tsx    # Professional Notion-style editing studio workstation
│   │   ├── services/
│   │   │   └── api.ts            # Typed REST client with deterministic local parser fallback
│   │   ├── types/
│   │   │   └── index.ts          # Shared TypeScript domain contracts
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── package.json
│   └── tailwind.config.js
│
├── backend/                      # Python FastAPI Processing Engine
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py         # Media uploads, beat analysis, plan & render endpoints
│   │   ├── core/
│   │   │   └── config.py         # Paths, storage, and automated FFmpeg discovery
│   │   ├── schemas/
│   │   │   └── editing_plan.py   # Pydantic v2 schemas for plans, jobs, and analysis
│   │   ├── services/
│   │   │   ├── audio_analysis.py # Librosa tempo (BPM) & transient beat detection
│   │   │   ├── command_interpreter.py # Deterministic NLP directive parser
│   │   │   ├── timeline_builder.py    # Beat-snapping multi-track timeline constructor
│   │   │   └── video_renderer.py      # Multi-clip FFmpeg compositor & title overlay
│   │   └── main.py               # FastAPI entrypoint with CORS & static media mounts
│   ├── storage/
│   │   ├── uploads/              # Uploaded photographs and audio tracks
│   │   └── exports/              # Rendered 1080×1920 MP4 reel files
│   └── requirements.txt
│
├── prisma/
│   └── schema.prisma             # Production PostgreSQL schema for projects, clips, and assets
├── tests/
│   ├── test_backend.py           # Unit tests for schemas, NLP, and timeline
│   ├── test_renderer.py          # FFmpeg MP4 rendering pipeline test
│   └── test_e2e_workflow.py      # End-to-end integration test of complete user workflow
└── README.md
```

### Long-Term Service Communication

```
Next.js Frontend  ──>  NestJS Application API (Prisma / PostgreSQL)  ──>  FastAPI Engine (Librosa / FFmpeg)
```

- **Frontend**: Next.js / React with Tailwind CSS design tokens.
- **Application Orchestration**: NestJS API with PostgreSQL and Prisma ORM for persistent project metadata, permissions, and media tracking.
- **Specialized Processing Service**: FastAPI service executing audio beat extraction, deterministic plan compilation, and FFmpeg video encoding.

---

## Design System Guidelines

- **Typography**: Clean, consistent sans-serif typography (`Inter` / `Geist`) across all headings, controls, inputs, and canvas overlays.
- **Palette**: Restrained monochrome palette: white (`#FFFFFF`) and soft off-white (`#FAFAFA`) surfaces, charcoal typography (`#18181B`), neutral gray borders (`#E4E4E7`), and subtle hover states (`#F4F4F5`).
- **No Gradients & No Emojis**: Crisp, solid fills and minimal line icons from `lucide-react`.
- **Rounded Geometry**: Consistent `rounded-lg` and `rounded-xl` borders for cards, dialogs, buttons, and panels.

---

## Core Capabilities

1. **Multi-Photo Upload & Management**: Drag-and-drop and batch selection with type validation, image reordering, and individual clip deletion.
2. **Audio Beat Synchronization**: Librosa estimates tempo (BPM) and transient downbeats, snapping cuts to rhythm.
3. **Interactive 9:16 Preview Player**: True vertical aspect ratio with preloaded image caching, play/pause synchronization, seeking/scrubbing, and audio playback.
4. **Interactive Multi-Track Timeline**: Visual clip tracks with direct clip duration adjustment (`[-] 2.5s [+]`), motion selector, and real beat markers.
5. **Deterministic Voice & Text Directives**:
   - `"Create a 20-second cinematic reel."`
   - `"Sync the cuts to the beats."`
   - `"Make the first photo last three seconds."`
   - `"Add a title at the beginning."`
   - `"Make the transitions smoother."`
   - `"Change the title to Summer Memories."`
6. **True FFmpeg Video Rendering**: Background video compositor producing genuine 1080×1920 MP4 files at 30 FPS with title cards and audio fade.
7. **Local State Persistence**: Projects are automatically persisted to `localStorage`, surviving page refreshes without data loss.

---

## Quickstart & Local Development

### Prerequisites
- **Node.js**: v18+ (tested on Node v24)
- **Python**: 3.10+ (tested on Python 3.10)
- **FFmpeg**: Automatically provided via `imageio-ffmpeg` static binary bundle.

### 1. Backend Setup (FastAPI)

```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
py -3.10 -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI engine (runs on port 8000)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup (React + Vite)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server (runs on port 5173)
npm run dev -- --host 127.0.0.1 --port 5173
```

Visit **`http://localhost:5173`** in your browser.

---

## Automated Verification & Testing

RayFlow AI includes comprehensive test suites:

```bash
# 1. Run Schema & Directive Parser Unit Tests
.\backend\venv\Scripts\python.exe tests\test_backend.py

# 2. Run End-to-End FFmpeg Video Rendering Test
.\backend\venv\Scripts\python.exe tests\test_renderer.py

# 3. Run Complete Integration Suite (Uploads, Librosa Beats, Directives, Export, Download)
.\backend\venv\Scripts\python.exe tests\test_e2e_workflow.py

# 4. Verify Frontend Compilation & TypeScript Types
cd frontend && npm run build
```

---

## REST API Specification

- `GET /api/health` — Service health check.
- `POST /api/media/images` — Upload multiple photographs.
- `POST /api/media/audio` — Upload audio soundtrack track.
- `POST /api/audio/analyze` — Run Librosa beat tracking and tempo estimation.
- `POST /api/commands/interpret` — Translate voice/text directives into structured editing plans.
- `POST /api/projects/plan` — Construct beat-synchronized timeline clips.
- `POST /api/render` — Trigger asynchronous FFmpeg MP4 rendering job.
- `GET /api/render/{job_id}` — Query render progress and status.
- `GET /api/render/{job_id}/download` — Download final 1080×1920 MP4 file.

---

## Inspiration & Acknowledgments

RayFlow AI is built with inspiration from filmmaker Satyajit Ray's principle: *"The director is the only person who knows what the film will look and sound like. How images cut together, how music enters and recedes — rhythm is everything."*
