# RayFlow AI — A beginner's guide

RayFlow AI turns photos, video clips, and audio into an edited video. You can arrange clips yourself, generate a first draft with **Auto Reel**, or describe changes to the **AI Director** and review its suggestions before applying them.

This guide takes you from opening the project for the first time to downloading a finished MP4. You do not need to know how to code. **Manual editing and Studio MP4 export do not require an AI API key.**

| Workspace | What it is for |
| --- | --- |
| **Studio** | Start here. Make a reel from photos or video, add music and captions, adjust cuts, and export an MP4. |
| **AI Editor** | A broader workspace for scripts, storyboards, media generation, design, timeline editing, grading, and sound. Some tools need additional services, and parts of its integration are still being verified. |

If someone has already started RayFlow for you, open their app link and skip to [your first video](#your-first-video-with-the-sample-reel). For a local installation, follow the setup below.

## Contents

- [Understand the basics](#understand-the-basics)
- [Install and start RayFlow on Windows](#install-and-start-rayflow-on-windows)
- [macOS and Linux setup](#macos-and-linux-setup)
- [Your first video with the sample reel](#your-first-video-with-the-sample-reel)
- [Make a video with your own files](#make-a-video-with-your-own-files)
- [Generate a draft with Auto Reel](#generate-a-draft-with-auto-reel)
- [Use the AI Director](#use-the-ai-director)
- [Add and edit captions](#add-and-edit-captions)
- [Save, back up, and reopen projects](#save-back-up-and-reopen-projects)
- [Explore the AI Editor](#explore-the-ai-editor)
- [Stop and restart the app](#stop-and-restart-the-app)
- [Troubleshooting](#troubleshooting)
- [Developer reference and further reading](#developer-reference-and-further-reading)

## Understand the basics

| Term | Plain-language meaning |
| --- | --- |
| **Project** | Your editable work: media references, timelines, captions, and settings. |
| **Clip** | One photo or a section of video placed in your edit. |
| **Timeline** | The strip at the bottom showing what plays, in what order, and for how long. |
| **Playhead** | The marker showing your current position in the video. Move it to inspect a particular moment. |
| **Trim** | Shorten the start or end of a clip. Your original uploaded file is retained. |
| **Transition** | How one clip changes into the next, such as a cut or a crossfade. |
| **Aspect ratio** | The shape of the video: tall, wide, or square. |
| **Render / export** | Turn the editable timeline into a video file you can watch or share. |
| **B-roll** | Extra footage or images that illustrate what is being said. |
| **API key** | A credential from an AI service that lets RayFlow use that service. Provider usage may cost money. |

When running locally, RayFlow has two parts that must stay running:

1. The **frontend** is the interface in your browser. Its usual address is `http://127.0.0.1:5173`.
2. The **backend** handles uploads, saves, audio analysis, and video rendering. Its address is `http://127.0.0.1:8000`.

`127.0.0.1` means “this computer.” A **terminal** is the window where you enter the startup commands. A **port**, such as `5173`, identifies which local service the browser should open.

## Install and start RayFlow on Windows

These instructions use **PowerShell**. In VS Code, choose **Terminal → New Terminal** and select PowerShell if needed. Enter each command, then press **Enter**. Wait for installation commands to finish before continuing.

### 1. Get the project folder

If the project is already open in VS Code, use that copy. Otherwise, download the repository using **Code → Download ZIP**, extract it, and choose **File → Open Folder** in VS Code.

Open the extracted folder containing `README.md`, `frontend`, and `backend`. This is the **repository root**. Do not run the app from inside the ZIP archive.

All Windows commands below start from that root unless stated otherwise. Check your terminal location:

```powershell
Get-Location
Get-ChildItem
```

You should see both `frontend` and `backend`. If not, open a terminal in the correct folder. When using `cd` to change folders, quote any path containing spaces, for example:

```powershell
cd "C:/Projects/Rayflow.ai"
```

Replace that example with the actual location of your project.

### 2. Install the required software

| Software | What to install | Why it is needed |
| --- | --- | --- |
| [Node.js](https://nodejs.org/en/download) | Version **24**, including npm | Starts and builds the browser interface and runs the internal editor worker. |
| [Python](https://www.python.org/downloads/) | **3.11** for a fresh setup | Runs the backend. An existing working Python 3.10 environment can be retained. |
| A browser | A current Chrome or Edge is a good starting point | Opens the editor; voice input depends on browser support. |
| FFprobe | Follow the next step | Reads uploaded media information and validates exports. |

When installing Python, include the Python launcher and select **Add python.exe to PATH** if offered. After installing Node or Python, reopen VS Code and its terminal so the commands become available.

Verify the installations:

```powershell
node --version
npm.cmd --version
py -3.11 --version
```

Expect Node to report `v24...`, npm to report a version number, and Python to report `Python 3.11...`. If you are keeping an existing Python 3.10 setup, use `py -3.10` instead of `py -3.11` when creating the environment below.

### 3. Make FFprobe available

**FFmpeg** creates the video; **FFprobe** inspects media files. The Python dependencies include an FFmpeg executable through `imageio-ffmpeg`, but they do **not** include FFprobe.

The simplest Windows setup is:

1. Download the [Gyan FFmpeg essentials ZIP](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip).
2. Extract it and open its `bin` folder.
3. Copy `ffprobe.exe` into this project's `backend/tools` folder.
4. Verify it from the repository root:

```powershell
./backend/tools/ffprobe.exe -version
```

You should see version information. If `ffprobe -version` already works in your terminal, you can use that installed copy instead. An alternative is to set `FFPROBE_PATH` to the executable's full path in `backend/.env`. See [FFprobe notes](backend/tools/README.md).

### 4. Install the backend dependencies

Create a **virtual environment**, a folder containing Python packages for this project:

```powershell
py -3.11 -m venv backend/venv
```

Skip that creation command if `backend/venv` is already a working environment. Install the required packages:

```powershell
./backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt -c backend/constraints.txt
```

The first installation needs internet access and may take several minutes. These commands use the environment's Python directly, so you do not need to run an activation script.

### 5. Create the configuration files

Run these commands from the repository root. They copy example settings only when the destination does not already exist, preserving existing configuration and keys:

```powershell
if (!(Test-Path backend/.env)) { Copy-Item .env.example backend/.env }
if (!(Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
```

The defaults are sufficient for the sample reel and manual editing. Leave API key fields empty for now. `backend/.env` configures the processing engine; `frontend/.env.local` tells the browser app how to reach it.

### 6. Install the frontend and editor worker dependencies

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix backend/editor-runtime ci
```

`ci` installs the versions recorded in the lockfiles. Run it for a fresh installation or when dependencies change, rather than every time you open the app. The second command prepares the internal worker used by AI Editor features; it does not start another public server.

### 7. Start the backend in terminal 1

From the repository root:

```powershell
./backend/venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Wait for **Application startup complete**. Leave this terminal running. It is normal that you do not get a fresh command prompt while the server is active.

### 8. Start the frontend in terminal 2

Open a **second terminal**, also at the repository root. Keep terminal 1 running:

```powershell
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Wait for Vite to print its local address. Open **[http://127.0.0.1:5173](http://127.0.0.1:5173)** in your browser. The `--strictPort` option makes a port conflict visible instead of silently opening the app on another port.

Use this same address each time. Switching between `localhost` and `127.0.0.1`, or between browser profiles, can give you a different guest session.

### 9. Check that everything is ready

Open these links in separate browser tabs:

| Address | Expected result |
| --- | --- |
| [Backend health](http://127.0.0.1:8000/api/health) | A JSON response showing that the backend is running. JSON is structured text; this page is not the editor. |
| [Backend readiness](http://127.0.0.1:8000/api/ready) | `"status": "ready"` with `storage`, `ffmpeg`, and `ffprobe` checks set to `true` in a local setup. |
| [Studio](http://127.0.0.1:5173/#/studio) | The editing workspace, possibly with a first-time welcome dialog. |

In the welcome dialog, choose **Skip for now** to edit without an AI connection. You can add a provider later through **Connections**.

The two servers being ready is enough to start. Speech models and AI services are optional and have their own setup steps below.

## macOS and Linux setup

The editing walkthrough is the same. Install Node 24, Python 3.11, and FFmpeg/FFprobe using the tools appropriate to your system. An FFmpeg installation through Homebrew on macOS or your Linux package manager normally includes FFprobe. Confirm that `node --version`, `python3.11 --version`, and `ffprobe -version` work.

From the repository root, install dependencies and copy configuration without replacing existing files:

```bash
python3.11 -m venv backend/venv
backend/venv/bin/python -m pip install -r backend/requirements.txt -c backend/constraints.txt
test -f backend/.env || cp .env.example backend/.env
test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local
npm --prefix frontend ci
npm --prefix backend/editor-runtime ci
```

Skip virtual-environment creation if you already have a working one. Start the backend in one terminal:

```bash
backend/venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in a second terminal:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open [Studio](http://127.0.0.1:5173/#/studio) and use the readiness checks above. In later commands, replace `./backend/venv/Scripts/python.exe` with `backend/venv/bin/python` and `npm.cmd` with `npm`.

## Your first video with the sample reel

This exercise uses four sample images provided by RayFlow. They may be labeled color cards on a fresh installation. A sample soundtrack is included when one is available locally; you can also complete the exercise without sound. You do not need your own media, an AI key, or a speech model.

### 1. Open a practice project

Open [Studio](http://127.0.0.1:5173/#/studio). If you already have work open, click **Projects**, enter a name such as **My first reel**, and click **Create project** so you have a separate place to practice.

On a fresh workspace, RayFlow creates an initial project automatically. The text field in the Studio toolbar lets you name the reel you are editing.

### 2. Load the example

In the left panel, select **Media**, then click **Try a Rayflow sample reel**. Wait for the media to load. You should see four media items, clips on the bottom timeline, and an image in the preview. If a soundtrack is available, it appears under **Music**; otherwise, this practice reel will be silent.

Use the sample button in a practice project: it loads sample media into the active reel.

### 3. Find the main controls

| Area | What you do there |
| --- | --- |
| Top navigation | Open **Studio**, **AI Editor**, **Dashboard**, **Connections**, **Projects**, or **Assets**. |
| Studio toolbar | Name the reel, choose its shape, undo changes, open **Auto Reel**, or **Export MP4**. |
| Left panel | Switch between **Media**, **Music**, **Captions**, **Inserts**, **Effects**, **Pacing**, and **Title**. Scroll the tab row sideways if needed. |
| Center preview | Watch the edit with **Play/Pause** and move the playback slider. |
| Bottom timeline | Select, reorder, and trim clips; inspect captions, inserts, and soundtrack beats. |
| Right panel | Enter instructions in **Rayflow AI Director** once a provider or Local commands is selected. |

On a smaller screen, use the toolbar's **Media** and **Director** buttons to reveal their panels. A larger desktop window gives you more room to edit.

### 4. Make three simple edits

1. Choose **9:16** in the toolbar for a tall phone video.
2. Open **Title**, enable **Show opening title**, and replace **Opening title** with `My first RayFlow video`. The supporting line is optional.
3. Click the first clip on the timeline. Use its **+** or **−** duration button to make it longer or shorter by half a second. The timeline updates to show the change.

Press **Play** beneath the preview. Click or drag on the timeline ruler to move to another moment. If you shorten a clip and want to restore it, use the toolbar's **Undo** button.

### 5. Export and download

1. Click **Export MP4** in the Studio toolbar.
2. Wait for the render dialog to report **Your Rayflow reel is ready**. Keep the backend running while it works; rendering time depends on your computer and the edit.
3. Click **Download MP4**. Your browser saves it to its download location, usually **Downloads**, or asks where to save it.
4. Open that file in a video player and check the picture, title, and sound if you included a soundtrack.

You can also choose **Watch in Preview** to inspect the rendered file inside RayFlow. **Canvas Mode** returns to the editable preview. If you change the edit afterwards, export again to create an updated video.

You now have a finished video file. To keep an editable backup as well, follow [project backups](#save-back-up-and-reopen-projects).

## Make a video with your own files

### 1. Create a project and choose the output shape

Click **Projects**, enter a name, and click **Create project**. In Studio, choose a ratio in the toolbar:

| Ratio | Export size in Studio | Typical use |
| --- | --- | --- |
| **9:16** | 1080 × 1920 | Reels, TikTok, and YouTube Shorts |
| **16:9** | 1920 × 1080 | Widescreen YouTube or desktop video |
| **1:1** | 1080 × 1080 | Square social posts |

Studio renders at 30 frames per second. **Fill Frame** crops media to fill the chosen shape. **Fit to Frame** keeps the whole photo or video visible, which can leave space around it. Hover over toolbar icons to see their labels.

### 2. Upload photos or video

Open **Media** and click **Bring your footage**, or drag files onto that area. Select several files together if needed.

| Type | Accepted file extensions in Studio |
| --- | --- |
| Photos | `.jpg`, `.jpeg`, `.png`, `.webp` |
| Video | `.mp4`, `.mov`, `.webm`, `.avi`, `.mkv` |
| Soundtrack, through Music | `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac` |

Start with a few photos or a short MP4. A file extension does not guarantee that every browser can play the codec inside it; an MP4 with H.264 video and AAC audio is a useful compatibility choice.

The default limit is **500 MB per file** and **1024 MB per upload request**. Upload large collections in smaller batches.

Wait for the upload to finish. RayFlow creates timeline clips from your media. Further uploads append clips to an existing edit.

### 3. Arrange and trim the clips

- Drag clips along the timeline to change their order.
- Click a clip to select it. Use the duration **+ / −** controls or drag its left/right edge to trim it.
- For a video, trimming the left edge changes where playback begins within the source file. You cannot extend it beyond the available footage.
- Choose **Zoom In**, **Zoom Out**, **Pan Left**, **Pan Right**, or **Static** from the selected clip's motion menu.
- Remove a selected clip with its trash button or **Delete/Backspace** while you are not typing in a field.
- Use the timeline zoom controls when a short clip is difficult to select.

The media list also has **Move Up**, **Move Down**, and removal buttons. Review the timeline after reordering media or changing pacing.

Useful Studio shortcuts work when you are not typing in a field or using a dialog:

| Action | Windows / Linux | macOS |
| --- | --- | --- |
| Undo | **Ctrl+Z** | **Cmd+Z** |
| Redo | **Ctrl+Shift+Z** or **Ctrl+Y** | **Cmd+Shift+Z** |
| Delete the selected clip, caption, or soundtrack | **Delete** or **Backspace** | **Delete/Backspace** |

Undo/redo applies to recorded timeline edits during the current session. Use a project archive for a lasting backup.

### 4. Add music and choose the pacing

Open **Music** and choose your soundtrack. RayFlow analyzes its rhythm automatically. When analysis succeeds, the panel displays **Tempo** in BPM (beats per minute) and **Beats Detected**.

Open **Pacing** to choose **Slow**, **Balanced**, or **Fast** cuts. Enable **Sync cuts to music** to align cuts with detected beats. If it was already enabled before the soundtrack was added, turn it off and on to request fresh alignment. Uploading music by itself preserves your existing clip edits.

Beat synchronization needs an analyzed soundtrack with detectable beats. Voice recordings or quiet ambient audio may not provide useful beat markers. Preview the result after changing pacing, because it changes clip timing.

### 5. Add a title, color, and transitions

Use **Title** for the opening text and optional supporting line. Use **Pacing → Color and mood** for presets such as Cinematic, Vintage, Noir, Vibrant, or Minimal.

Use **Effects** for transitions. Select a transition between clips to edit it, then preview that boundary. Start with one or two changes so you can see what each control does.

**Inserts** contains B-roll and visual-layer controls. These are optional. Pixabay search needs its backend API key; background replacement needs an additional local segmentation model. Neither is required for a basic photo or video edit.

### 6. Check and export

Play the whole edit once. Check that faces are not cropped unintentionally, text is readable, and the sound is appropriate. Then use **Export MP4 → Download MP4** as in the sample exercise.

## Generate a draft with Auto Reel

**Auto Reel** builds a starting edit from your uploaded photos or primary video. It is separate from the conversational AI Director.

1. Upload your media and choose the aspect ratio first.
2. Click **Auto Reel** in the Studio toolbar.
3. Choose **Cinematic Story**, **Minimalist Clean**, or **Fitness High Energy**.
4. Set the optional features below.
5. Click **Generate Reel Draft** and wait for the processing stages to finish.
6. Review the resulting timeline, captions, and sound. Adjust anything you want before exporting.

| Auto Reel option | When to enable it |
| --- | --- |
| **Generate captions from speech** | Your audio/video contains speech and a local speech model is ready. |
| **Find contextual B-roll on Pixabay** | You have configured Pixabay and want extra visuals related to the speech. |
| **Trim greetings and long quiet pauses in new drafts** | You want a tighter spoken draft; review the resulting cuts. |
| **Add clicks to spoken list items** | Your speech contains a list and you want accompanying sound cues. |
| **Whisper model** | Select a verified, ready model when using speech-dependent features. |

For your first photo-and-music draft without extra setup, **uncheck captions, contextual B-roll, spoken-list clicks, and speech trimming**. This avoids requesting speech or stock-media features you have not configured.

A draft changes the active timeline; it does not download an MP4. Use Undo during the current session if needed, and use **Export MP4** when the draft is ready. Keep an archive before experimenting with a project you want to preserve.

## Use the AI Director

### Connect a provider

1. Open **Connections** in the top navigation.
2. Find a supported Director provider, such as **Google Gemini**, **OpenAI**, or **Anthropic**. Enter your own API key in its **API key** field.
3. Choose a **Preferred model**, click **Save**, then **Test connection**. Wait for the result.
4. At the top of Connections, choose that provider under **Studio AI director** and click **Save preference**.
5. Return to **Studio**.

Saving a provider in the first-time setup also selects it for the Director. On the regular Connections page, use **Save preference** explicitly. A successful connection test checks connectivity; it does not guarantee that every edit request will be understood correctly.

For Gemini, use a key from [Google AI Studio](https://aistudio.google.com/apikey). Choose a **Preferred model** from the dropdown, or save your key and click **Find models** for your account's current text models. Save again after changing the model. **Test connection** checks the key and model currently entered; testing a draft does not save it. The selected Gemini model is used by Studio Director and AI Editor text generation. Tests do not generate content; quota or billing can still prevent generation. Invalid keys, restricted API access, and unavailable models have separate error messages.

Keys are stored encrypted on the backend. Use the Connections fields for provider keys; never place secrets in frontend files or variables beginning with `VITE_`. Hosted provider requests need internet access and may incur charges from your provider.

### Request and review an edit

Type into **Tell Rayflow what to edit…** in the right-hand Director panel and press **Enter** or the send button. Use **Shift+Enter** for a new line. If your request concerns one clip or caption, select it first.

Examples to try, one at a time:

```text
Change the title to Summer Memories.
Change the video to square.
Remove all captions.
Make the transitions smoother.
Trim the selected clip to three seconds.
Undo the last change.
```

When RayFlow opens **Review your Rayflow edit**, read the proposed actions. Choose **Approve and apply** to update the timeline or **Cancel** to keep the current edit. Preview the result after applying it. Ask for undo or redo separately from other edits.

The Director receives editing context such as the timeline, captions/transcript, selection, playhead, and recent conversation. Be specific about which clip, duration, or text you mean. It can work with an existing transcript, but generating new speech captions uses the Captions workflow below.

If a provider request fails, RayFlow shows an error. **Automatic does not silently switch to Local commands after a provider failure.** Check Connections and retry when the provider is ready.

### Use basic commands without a paid provider

In **Connections → Studio AI director**, choose **Local commands** and click **Save preference**. This uses a limited rule-based parser; it does not need an AI service. Try `Change the title to Summer Memories` or `Change the video to landscape`. Use the manual controls for requests it does not recognize.

For a local language model, install [Ollama](https://ollama.com/), download a model with `ollama pull qwen3:8b`, and make sure Ollama is running. In `backend/.env`, set:

```dotenv
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_GENERATION_TIMEOUT=180
```

Restart the backend, then choose **Ollama** under **Studio AI director** and save the preference. Local inference can be slow and needs enough memory for the model. On a hosted RayFlow installation, the model service must be reachable from the backend host.

Both workspaces now share the Ollama address and saved model in **Connections**. A local development backend uses `http://127.0.0.1:11434` by default; `EDITOR_OLLAMA_URL` takes precedence over `OLLAMA_HOST`. Choose **Find models**, save an installed model, then **Test connection**. Discovery checks that the service and model are present; generation also needs enough free memory. CPU planning with `qwen3:8b` can take two to three minutes. If Ollama cannot allocate memory, close memory-heavy applications or choose a smaller installed model.

### Use Agent Router

Choose the **Agent Router** card in Connections, enter your Agent Router key and the exact model ID supplied by your account, then save. **Find models** asks the gateway for its catalog. **Test connection** sends a short generation request and may consume provider credit. Select **Agent Router** under **Studio AI director** and save the preference. The same selection is used by AI Editor assistant **Chat** mode.

The default endpoint is `https://agentrouter.org/v1`. The backend operator can set `AGENTROUTER_BASE_URL=https://co.agentrouter.org/v1` for an account using that gateway. A gateway key belongs in the Agent Router card. HTTP 401 means the gateway rejected the credentials; it does not verify access to Opus or Astra.

### Speak instead of typing

Click the microphone in the Director panel and allow microphone access if your browser asks. Speak the instruction; RayFlow submits the recognized instruction automatically. Review the resulting proposal before applying it. If the browser misheard you, cancel the proposal and type the corrected instruction. Browser speech recognition availability varies. This is separate from transcribing speech in an uploaded video.

The microphone shows an animated waveform while listening, and the text field shows words as they are recognized. Only the completed utterance is submitted. In **AI Editor**, select a timeline clip, open **Inspector → Assistant**, use **Chat** mode, and click its microphone. Its assistant applies supported tools directly; use **Undo** to restore an edit.

Select a visual timeline clip and try `Rotate the selected clip clockwise by 90 degrees`, `Move the selected clip left a little`, or `Center the selected clip and reset its rotation`. Studio presents a proposal before applying these edits. Moving the picture changes its position within the frame; `Move this clip to the end of the timeline` is a separate Studio reorder command. Static position and rotation are included in both Studio MP4 and AI Editor HQ exports. AI Editor preserves position animation by asking you to disable it before a static move. Transfers between workspaces may reject transformed clips because their canvas fitting differs.

## Add and edit captions

Captions are timed text shown over your video. You can add them manually, import supported JSON, or generate them from speech.

### Option A: Add captions yourself

1. Open **Captions** in the left panel.
2. Move the playhead to an uncaptioned part of the timeline.
3. Click **+ Add caption**.
4. Replace the placeholder text and adjust its **Start** and **End** times.
5. Choose a caption style and preview the result.

Manual captions do not require a speech model or provider key.

### Option B: Generate captions from speech

Automatic transcription uses a local **Faster-Whisper** speech model. A fresh install does not download its model weights automatically.

In another terminal at the repository root, run this one-time download:

```powershell
./backend/venv/Scripts/python.exe backend/setup_local_assets.py --whisper small
```

`small` is a lighter starting point. Use `--whisper medium` if you want a larger model and have the memory and processing time available. The download requires internet access and disk space; once cached, transcription can run locally. The default configuration uses cached models only.

Then:

1. Upload a video with speech or a spoken audio file and place the relevant media in your edit.
2. Open **Captions** and choose the correct **Speech source**.
3. Click **Check local models**. Wait for verification and select a model marked ready. A model marked **not cached** cannot be selected yet.
4. Leave **Language** blank for automatic detection, or enter a language code such as `en`, `hi`, or `kn`.
5. Click **Generate speech captions** and wait for processing.
6. Read through the transcript and correct names, spelling, punctuation, and timing before export.

A music-only file may produce no captions. CPU transcription can take time, especially with longer recordings or larger models.

### Edit, delete, import, or download captions

- Edit text and start/end times in **Your captions**. Click outside an edited field to commit it.
- Select a caption in the list, timeline, or preview. Press **Delete/Backspace** outside a text field to remove it. Use **Shift/Ctrl/Cmd-click** to select multiple captions.
- Use **Undo** to recover a deletion during the current editing session.
- Use **Smart phrases** to regroup existing timed words into phrases.
- **Romanize captions** converts supported Devanagari and Kannada text to Roman letters; review spelling afterwards.
- Use **Import caption JSON** for RayFlow caption JSON or a compatible Caption Engine transcript. For a source transcript, choose its matching speech source first. This button imports JSON, not SRT or VTT.
- Choose **SRT**, **WebVTT**, **ASS (styled)**, or **Editable JSON**, then click **Download captions** to save a separate subtitle file.

MP4 export renders enabled captions into the picture. Separate SRT/VTT files carry text and timing; they do not preserve all the visual styling shown in the preview.

## Save, back up, and reopen projects

### How saving works

Studio automatically saves edits to the backend project after a short pause, and keeps a browser-local snapshot. Leave the backend running while editing and give the save a moment to finish before closing the browser. Navigation between workspaces also attempts to save first.

If **Autosave failed** appears, resolve it before leaving. Clearing site data or changing browsers can lose access to a guest workspace even if its files still exist on the backend. Undo/redo history is temporary and resets when a project is loaded.

### Make an editable backup

1. Pause editing and allow autosave to finish.
2. Click **Projects**.
3. Click **Download** beside your project, or open **Sequences and files → Download project archive**.
4. Keep the downloaded ZIP somewhere you can find it, alongside your original source media.

To restore a copy, open **Projects**, choose **Import a project archive or JSON**, and select your saved file. An archive packages project data and collected media; plain project JSON may still need its media to be available.

To continue an existing project, open the same app address in the same browser profile, click **Projects**, and select its name. **Sequences and files** lets you open a saved sequence or transfer a copy between Studio and AI Editor. A sequence is another timeline within the project. Transfers can reject features that the destination cannot represent.

### Choose the right download

| Download | Use it when you want to… |
| --- | --- |
| **Export MP4** in Studio | Watch or share the finished video, including rendered text, transitions, and audio. |
| **Download project archive** in Projects | Back up or move editable work. |
| **Export timeline** in Studio | Download an `.otio` timeline for compatible editing tools. It includes cut timing, source trims, and media references. |
| **Download captions** in Captions | Save subtitles separately from the video. |

An OTIO file is not a playable video or a self-contained media backup. RayFlow-specific captions, grading, transitions, overlays, and sound processing are retained as metadata; another editor may not reproduce their appearance. Use MP4 for the final rendered result.

### Find completed exports later

Open **Dashboard** to inspect processing history and completed render jobs. Use **Download MP4** next to a completed Studio render. An **interrupted** job means processing did not finish before the backend stopped; rerun it after restarting.

With default local settings, backend data lives under `backend/storage`, including workspace-specific uploads and exports. Keep that directory to retain saved media and results. Download archives before moving to another installation; backend files alone do not transfer your browser's guest session.

## Explore the AI Editor

Open **AI Editor** in the navigation or visit [http://127.0.0.1:5173/#/editor](http://127.0.0.1:5173/#/editor). It uses the same workspace session, project manager, shared assets, and provider connections, but has a separate timeline representation.

For a first exploration:

1. Create a practice project through **Projects**.
2. Open **Import** to bring in media, or open **Assets** in the shared navigation to insert an existing asset.
3. Use its timeline controls to assemble a short edit and preview it.
4. Explore **Project**, **Script**, or **Scene Wall** for planning; **Design** for graphic assets; and **Grading** or **Sound** for picture and audio adjustments.
5. Open **Export** and check the available format and capability messages before rendering.

Generation workspaces need the corresponding provider or local service configured. Connecting one Director provider does not automatically enable every image, video, voice, or 3D tool.

The current AI Editor **Quick browser export records video only**. Use **HQ FFmpeg** for timeline audio. Its HQ path currently rejects certain features, including text overlays, transitions, chroma key, non-normal blend modes, and opacity keyframes. A title baked into a PNG is supported. These limits belong to the AI Editor export path; Studio has its own renderer.

For a simple captioned reel, follow the Studio walkthrough first. See the [AI Editor implementation report](docs/ai-editor-integration.md) and [feature inventory](docs/ai-editor-inventory.md) for verified behavior and remaining work. Live providers and hosted deployment still need environment-specific verification.

## Stop and restart the app

After saving your project and finishing any exports, press **Ctrl+C** in each running server terminal. If PowerShell asks whether to terminate a batch job, confirm with `Y` and Enter.

Next time, open two terminals at the repository root and run only these startup commands:

**Terminal 1 — backend:**

```powershell
./backend/venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — frontend:**

```powershell
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open [Studio](http://127.0.0.1:5173/#/studio). You do not need to recreate the environment, recopy configuration, or redownload cached models on every launch.

## Troubleshooting

| What you see | What to check or do |
| --- | --- |
| `node`, `npm.cmd`, or `py` is not recognized | Install the required software, then reopen VS Code and the terminal. Use the version checks from setup. |
| Python 3.11 cannot be found | Install Python 3.11 with the launcher, or use `py -3.10` if retaining the documented working Python 3.10 setup. |
| PowerShell says `npm.ps1` cannot run | Use `npm.cmd` exactly as shown. The setup uses the environment's Python directly, so activating `venv` is unnecessary. |
| A path or `requirements.txt` cannot be found | Run `Get-Location` and `Get-ChildItem`. Start commands in the folder containing both `frontend` and `backend`. |
| Dependency installation fails | Check internet access, Python/Node versions, and the first terminal error. Use `npm ci` with the supplied lockfiles and the Python constraints command shown above. |
| Port 5173 or 8000 is already in use | Check whether RayFlow is already running in another terminal. Use that instance or stop your older instance with Ctrl+C before starting again. |
| The browser says the site cannot be reached | Keep both server terminals open, check startup errors, and use `http://127.0.0.1:5173`. |
| “The video engine could not be reached” | Check backend health on port 8000. Ensure `frontend/.env.local` uses `/api` and its proxy target is `http://127.0.0.1:8000`; restart the frontend after changing that file. **Continue offline** does not start the backend or enable uploads/rendering. |
| Health works but readiness fails | Read the failed readiness check. Verify FFprobe, disk space, and that the backend can write to its storage directory. |
| `ffprobe` is missing | Put `ffprobe.exe` in `backend/tools`, install it on PATH, or set `FFPROBE_PATH` in `backend/.env`; restart the backend and check readiness again. |
| Upload is rejected or preview will not play | Use a listed format, stay within upload limits, and try a short H.264/AAC MP4 to check codec compatibility. |
| Beat analysis failed | The soundtrack may have no clear beat. Continue editing manually or try another track; inspect the error if it fails on all files. |
| **Generate Reel Draft** is disabled | Upload visual media first. If no speech model is ready, disable captions, contextual B-roll, and spoken-list clicks, or cache a model and check again. |
| “No verified model” or “not cached” | Run the speech-model download command, then click **Check local models** and wait for verification. |
| Captions are empty or incorrect | Select the source containing speech, check the language, and review recording quality. Music-only sources may have no speech; edit transcription mistakes manually. |
| Director reports a missing key, authentication error, or rate limit | Open **Connections**, check provider and model, test the connection, and save the Director preference. Check the provider account's access/usage limits. |
| The microphone does not work | Allow browser microphone access and use a supported browser. You can type the instruction instead. |
| Pixabay/B-roll is unavailable | Configure `PIXABAY_API_KEY` in `backend/.env` and restart the backend, or disable contextual B-roll and use your own media. |
| **Autosave failed** or an edit conflict appears | Keep the page open, restore the backend connection, and avoid editing the same project in multiple tabs. Preserve a backup before reloading or switching projects. |
| A project appears missing in another browser | Return to the original browser profile and app address, then export an archive to move it. Guest sessions are not automatically shared across browsers. |
| Export is queued or slow | Another job may be running; Studio's default render concurrency is one. Keep the backend running and inspect **Dashboard** or the render dialog. |
| Export failed or was interrupted | Read the error in the dialog/backend terminal, check readiness and disk space, then try a short edit. Restarted backends require unfinished jobs to be rerun. |
| AI Editor reports a missing worker/module | Run `npm.cmd --prefix backend/editor-runtime ci` from the repository root and retry. |
| AI Editor Quick export has no sound | Choose HQ FFmpeg; Quick browser export currently records video only. |

If you need help diagnosing a failure, include what you clicked, the visible error, your operating system, and the relevant terminal error. Omit API keys and other credentials.

## Developer reference and further reading

### What runs where

```text
Browser: React 19 + TypeScript + Vite
    |
    | /api requests through the Vite development proxy
    v
FastAPI backend: projects, sessions, uploads, providers, jobs
    |-- FFmpeg / FFprobe: media processing and export
    |-- Librosa: soundtrack analysis
    |-- Faster-Whisper: optional local speech transcription
    |-- Internal Node worker: integrated AI Editor SDK/media operations
    `-- Optional remote providers or local model services
```

Local setup does not require a PostgreSQL database. `prisma/schema.prisma` is an architectural reference and is not connected to the current runtime. Shared project persistence is handled by the backend; browser storage also retains local snapshots and preferences. Hosted editor configuration uses Supabase as described in its deployment guide.

| Path | Purpose |
| --- | --- |
| `frontend/src/pages/StudioPage.tsx` | Studio interface and editing workflow |
| `frontend/src/components/studio/` | Timeline, captions, effects, and inserts |
| `frontend/src/features/ai-editor/` | Integrated advanced editor, with its own LICENSE and NOTICE |
| `frontend/src/services/` | API access, workspace sessions, and shared projects |
| `backend/app/api/` | Backend routes |
| `backend/app/services/` | Audio analysis, speech, captions, AI plans, and rendering |
| `backend/app/editor/` | Editor projects, ownership, provider connections, and jobs |
| `backend/editor-runtime/` | Internal Node worker and dependencies |
| `backend/storage/` | Default local data directory; override with `RAYFLOW_STORAGE_DIR` |
| `tests/` | Backend, frontend, rendering, and browser checks |
| `docs/` | Deployment guides and implementation reports |

### Configuration reference

| Setting | Where / purpose |
| --- | --- |
| `VITE_API_BASE_URL=/api` | `frontend/.env.local`; browser API path, not a secret |
| `RAYFLOW_API_PROXY_TARGET=http://127.0.0.1:8000` | `frontend/.env.local`; local Vite proxy destination |
| `RAYFLOW_STORAGE_DIR` | `backend/.env`; optional local storage override |
| `FFPROBE_PATH` | `backend/.env`; optional absolute path to FFprobe |
| `PIXABAY_API_KEY` | `backend/.env`; optional stock-media search credential |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Optional backend environment configuration; OpenRouter is also available in Connections |
| `OLLAMA_HOST`, `OLLAMA_MODEL` | Backend address and installed model for Ollama |
| `WHISPER_LOCAL_ONLY=true` | Use cached speech models; download them explicitly with the setup script |
| `MAX_UPLOAD_MB`, `MAX_REQUEST_MB` | Default file/request limits: 500 / 1024 |

Restart the relevant server after editing its environment file. Process environment values take precedence over dotenv files; saved provider settings can override defaults. Production configuration differs from local development, so follow the deployment guide for your target environment.

### Optional development checks

These are for contributors and are not required to use the editor. From the repository root on Windows:

```powershell
./backend/venv/Scripts/python.exe -m pip install -r tests/requirements.txt
./backend/venv/Scripts/python.exe -m pytest tests/test_backend.py tests/test_renderer.py tests/test_e2e_workflow.py
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run test:editor
npm.cmd --prefix frontend run build
```

Render/integration checks need the media tools installed and may take longer than unit tests. Browser checks require additional Playwright setup; see the verification reports for scope and recorded results.

With the backend running, [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) shows the generated API reference. Private project and media requests require the appropriate workspace session. Useful Studio endpoints include:

| Method and path | Purpose |
| --- | --- |
| `GET /api/health`, `GET /api/ready` | Liveness and processing readiness |
| `POST /api/media/images`, `POST /api/media/audio` | Visual media and soundtrack upload |
| `POST /api/audio/analyze` | Soundtrack beat analysis |
| `POST /api/commands/interpret` | Basic directive interpretation |
| `POST /api/ai/plan` | Generate a validated proposal for review |
| `POST /api/ai/apply` | Validate and apply approved editing actions |
| `POST /api/projects/plan` | Build a timeline |
| `POST /api/render` | Start an MP4 render |
| `GET /api/render/{job_id}` | Read render status |
| `GET /api/render/{job_id}/download` | Download a completed MP4 |

### Further reading

- [Local development and deployment](docs/deployment.md): environment variables, containers, storage, and operations.
- [Hosted AI Editor deployment](docs/hosted-editor-deployment.md): Vercel, Render, Supabase, and production configuration.
- [Director integration](docs/director-integration.md): current provider behavior, supported actions, and verification limits.
- [AI Editor implementation report](docs/ai-editor-integration.md) and [feature inventory](docs/ai-editor-inventory.md): integration status and remaining acceptance work.
- [Measured analytics](docs/analytics.md): what Dashboard numbers mean.
- [Phase 5–8 verification](docs/phases-5-8-report.md): earlier implementation and test evidence.
- [Ollama diagnostics](docs/ollama.md): model-server connectivity background. Some UI/fallback descriptions there predate the current Director; use this README and the Director report for current selection behavior.
- [Design guidelines](design.md): typography, palette, and interface conventions.

RayFlow draws inspiration from filmmaker Satyajit Ray's attention to the rhythm of images, sound, and cuts.
