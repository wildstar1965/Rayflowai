# RayFlow AI — Voice-Driven Cinematic Reel Studio

> *"The director is the only person who knows what the film will look and sound like. How images cut together, how music enters and recedes — rhythm is everything."*
> — **Satyajit Ray (1921–1992)**

**RayFlow AI** is a voice-first cinematic video-editing workstation created as a tribute to legendary filmmaker Satyajit Ray. It transforms photographs, music tracks, and natural-language voice directions into polished, beat-synchronized cinematic reels and exports genuine, downloadable 1080×1920 MP4 video files.

---

## 🌟 Core Features & Priorities (P0 Implemented)

- **Voice-First Directing & Natural Language Editing**: Speak your creative vision using speech recognition or text fallback. The deterministic natural-language interpreter parses duration, pacing, aspect ratio, style presets, and title overlays.
- **Audio Analysis & Beat Synchronization**: Powered by **Librosa** and **NumPy** in the backend. Automatically calculates tempo (BPM), detects transients and strong beats, and synchronizes cut points according to chosen pacing strategies (*Slow*, *Balanced*, *Fast*, *Beat-Driven*).
- **Kinetic Motion & Cinematic Styling**: Applies Ken Burns zoom-ins, zoom-outs, pans, and color grading filters (*Director Ray*, *Film Noir*, *Vintage Kodachrome*, *Vibrant Neo*, *Minimal Studio*).
- **True FFmpeg Video Rendering Engine**: Real end-to-end MP4 video encoding using **FFmpeg** (1080×1920 @ 30fps H.264 / AAC) with customizable gradient title cards and audio fadeouts.
- **Interactive Multi-Track Timeline**: Features time markings, image clip blocks, audio track with real beat markers, and playhead scrubbing.
- **Five React Bits Components Seamlessly Integrated**:
  1. `<SoftAurora />`: Deep blue and violet ambient WebGL2 hero background.
  2. `<MaskedHeading />`: Cinematic typography reveal with GSAP, SVG mask, spotlight, and parallax.
  3. `<SpecularButton />`: WebGL2 glass button with interactive light refraction for primary CTAs.
  4. `<StaggeredMenu />`: Fluid GSAP navigation panel with layered underlays adapted to RayFlow's dark palette.
  5. `<Stepper />`: 4-step guided creation modal (*Media*, *Music*, *Direct*, *Render*).

---

## 🏗 System Architecture

```
Rayflow.ai/
├── frontend/                     # React + TypeScript + Vite + Tailwind CSS
│   ├── src/
│   │   ├── components/
│   │   │   └── ui/               # The 5 integrated React Bits components
│   │   │       ├── MaskedHeading.tsx
│   │   │       ├── SoftAurora.tsx
│   │   │       ├── SpecularButton.tsx
│   │   │       ├── StaggeredMenu.tsx
│   │   │       └── Stepper.tsx
│   │   ├── pages/
│   │   │   ├── LandingPage.tsx   # Cinematic landing page
│   │   │   └── StudioPage.tsx    # Full editing workstation
│   │   ├── services/
│   │   │   └── api.ts            # REST client for backend
│   │   ├── types/
│   │   │   └── index.ts          # Strongly typed schemas
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── tailwind.config.js
│
├── backend/                      # Python FastAPI + Librosa + FFmpeg
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py         # REST endpoints for media, commands, rendering
│   │   ├── core/
│   │   │   └── config.py         # App configuration & FFmpeg discovery
│   │   ├── schemas/
│   │   │   └── editing_plan.py   # Pydantic models for plans, jobs, audio analysis
│   │   ├── services/
│   │   │   ├── audio_analysis.py # Librosa tempo & beat tracking
│   │   │   ├── command_interpreter.py # Natural language NLP parser
│   │   │   ├── timeline_builder.py    # Beat-synced timeline constructor
│   │   │   └── video_renderer.py      # FFmpeg video compositor & title overlay
│   │   └── main.py               # FastAPI application entrypoint
│   └── requirements.txt
│
├── tests/
│   ├── test_backend.py           # Unit tests for schemas, NLP, and timeline
│   └── test_renderer.py          # End-to-end FFmpeg rendering integration test
├── README.md
└── .gitignore
```

---

## 🚀 Getting Started

### Prerequisites
- **Node.js**: v18+ (tested on v24.15.0)
- **Python**: 3.10+ (tested on Python 3.10)
- **FFmpeg**: Automatically provided via `imageio-ffmpeg` static binary bundle.

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (Python 3.10)
py -3.10 -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server (runs on port 8000)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Start Vite development server (runs on port 5173)
npm run dev -- --host 127.0.0.1 --port 5173
```

Visit **`http://localhost:5173`** in your browser.

---

## 🧪 Testing

RayFlow AI comes with automated unit and integration tests:

```bash
# Run schema and command interpreter unit tests
.\backend\venv\Scripts\python.exe tests\test_backend.py

# Run end-to-end FFmpeg MP4 rendering pipeline test
.\backend\venv\Scripts\python.exe tests\test_renderer.py
```

---

## 📡 API Reference

- `GET /api/health` — Service health check.
- `POST /api/media/images` — Upload multiple photographs.
- `POST /api/media/audio` — Upload a music track.
- `POST /api/audio/analyze` — Run Librosa beat tracking & tempo analysis.
- `POST /api/commands/interpret` — Interpret voice/text editing commands.
- `POST /api/projects/plan` — Construct or update beat-synced timeline.
- `POST /api/render` — Trigger background FFmpeg video rendering job.
- `GET /api/render/{job_id}` — Check render progress & status.
- `GET /api/render/{job_id}/download` — Download rendered MP4 video.
