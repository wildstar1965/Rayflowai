# Voice editing and provider verification

## Using the changes

1. Open Connections and choose Ollama or Agent Router under Studio AI director. Save the preference. AI Editor assistant Chat mode uses this selection too.
2. For Ollama, find and save an installed model. The local development default is `http://127.0.0.1:11434`; `EDITOR_OLLAMA_URL` overrides `OLLAMA_HOST`. Model selection is shared between workspaces.
3. Select a visual timeline clip. In Studio, use the Director microphone. In AI Editor, use Inspector → Assistant → Chat → microphone.
4. Say “Rotate the selected clip clockwise by 90 degrees” or “Move the selected clip right a little.” Studio asks you to review the proposal. AI Editor applies supported tools directly. Undo restores the previous timeline state.

The microphone shows interim words and an animated waveform. Only final speech is submitted. Denied permission, missing input devices, and speech-service failures produce actionable errors. Leaving the component or disabling voice input cancels recognition. Reduced-motion preferences disable the waveform animation.

## What was fixed

- AI Editor previously required `EDITOR_OLLAMA_URL` even when Studio could discover the default local Ollama service. Both now resolve the same address and model.
- Studio previously sent Ollama directions to a limited settings interpreter. It now uses the validated Director action registry and review/apply flow, including clip position and rotation.
- The local prompt exceeded Ollama's default context and was truncated. Local plans now use compact schemas and an explicit 8192-token context. Oversized requests fail visibly instead of sending an oversized local prompt.
- Qwen3 uses its native non-thinking chat API for AI Editor text commands. Local movement tools specify one direction, while rotation uses a separate tool; this avoids mixing relative movement with absolute center coordinates.
- Agent Router has a separate encrypted credential entry, model discovery, connection test, and routing to its HTTPS gateway. Keys are not embedded in frontend configuration.
- Clip rotation and position are rendered by both Studio MP4 and AI Editor HQ FFmpeg export. AI Editor also exposes a Rotation slider. Transfers reject Studio transforms that the other workspace's fitting rules would change.

## Verification and limits

- Backend provider, action, and transport regression checks passed, including workspace isolation, credential redaction, relative transforms, invalid values, and shared Ollama settings.
- Two real MP4 render tests passed pixel checks for clockwise rotation, rightward movement, and the exposed black border.
- Frontend timeline tests and the local model/transform unit tests passed. The production build passed.
- All three browser voice checks passed, exercising simulated browser speech events with real editor tools and persistence. The existing Director browser checks also passed. Physical microphone recognition was not tested.
- A live Studio request to `qwen3:8b` produced and applied a 90-degree rotation and a 5% rightward offset. It took about 174 seconds while other verification was running.
- The final captured AI Editor request also succeeded against live Ollama in about 92 seconds. It returned exactly `rotateSelectedClip(degrees=90)` and `moveSelectedClip(direction="right", percent=5)`, with no vertical movement.
- Agent Router returned HTTP 401 for model discovery and minimal requests naming `claude-opus-5-5` and `gpt-6-astra`. Those responses establish credential rejection; they do not establish whether the account has those models. No working Agent Router generation was verified, and the supplied credential was not saved in project files.

Ollama also reported an insufficient-memory error during a cold load. Later inference succeeded. An 8B model can still be slow or fail to load under memory pressure; close memory-heavy applications or select a smaller installed model. Browser speech recognition is separate from Ollama and can require an internet connection.

Reproduction checks: `tests/test_voice_editing.py`, `tests/test_voice_rendering.py`, `tests/test_voice_browser.py`, and `frontend/src/features/ai-editor/utils/assistantTransform.test.ts`. Browser checks run through `tests/run_browser_checks.py` against isolated services.
