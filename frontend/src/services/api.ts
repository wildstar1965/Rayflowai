import {
  EditingPlan,
  AudioAnalysisResult,
  UploadedImage,
  UploadedAudio,
  CommandResponse,
  RenderJobStatus,
  TransitionConfig,
  AIEditingPlan,
  TranscriptionJob,
  CaptionFormat,
} from '../types';
import { getWorkspaceSession, uploadEditorAsset, editorRequest } from './editorClient';

const configuredApiBase = (import.meta.env?.VITE_API_BASE_URL || import.meta.env?.VITE_API_URL) as string | undefined;
const API_BASE = (configuredApiBase || '/api').replace(/\/$/, '');
const API_ORIGIN = API_BASE.replace(/\/api\/?$/, '');

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(6000) });
    return res.ok && (await res.json()).status === 'healthy';
  } catch {
    return false;
  }
}

export async function uploadImages(files: File[]): Promise<UploadedImage[]> {
  if (getWorkspaceSession()?.storage === 'supabase') {
    const uploaded: UploadedImage[] = [];
    for (const file of files) {
      const asset = await uploadEditorAsset(file);
      uploaded.push(await editorRequest(`/editor/assets/${asset.id}/studio`, { method: 'POST' }));
    }
    return uploaded;
  }
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }

  const res = await fetch(`${API_BASE}/media/images`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Image upload failed' }));
    throw new Error(err.detail || 'Image upload failed');
  }

  const data = await res.json();
  return data.images;
}

export async function uploadAudio(file: File): Promise<UploadedAudio> {
  if (getWorkspaceSession()?.storage === 'supabase') {
    const asset = await uploadEditorAsset(file);
    return editorRequest(`/editor/assets/${asset.id}/studio`, { method: 'POST' });
  }
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/media/audio`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Audio upload failed' }));
    throw new Error(err.detail || 'Audio upload failed');
  }

  return await res.json();
}

export async function loadDemoProject(): Promise<{ images: UploadedImage[]; audio: UploadedAudio | null }> {
  const res = await fetch(`${API_BASE}/media/demo-project`, {
    method: 'POST',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to load demo project' }));
    throw new Error(err.detail || 'Failed to load demo project');
  }

  return await res.json();
}


export async function analyzeAudioFile(filename: string): Promise<AudioAnalysisResult> {
  const formData = new FormData();
  formData.append('filename', filename);

  const res = await fetch(`${API_BASE}/audio/analyze`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Audio analysis failed' }));
    throw new Error(err.detail || 'Audio analysis failed');
  }

  return await res.json();
}

export function localInterpretCommand(command: string, currentPlan?: EditingPlan): CommandResponse {
  const plan: EditingPlan = currentPlan
    ? JSON.parse(JSON.stringify(currentPlan))
    : {
        duration_seconds: 15.0,
        aspect_ratio: '9:16',
        fit_mode: 'fill',
        style: 'cinematic',
        beat_sync: true,
        cut_pacing: 'balanced',
        motion: 'slow_zoom',
        title: { enabled: true, text: 'RAYFLOW', gradient: ['#FFFFFF', '#CCCCCC'] },
        clips: [],
        transitions: []
      };

  if (!plan.transitions) plan.transitions = [];
  if (!plan.fit_mode) plan.fit_mode = 'fill';

  const text = command.trim();
  const lower = text.toLowerCase();
  const changes: string[] = [];

  const wordMap: Record<string, number> = {
    first: 0, '1st': 0, '1': 0, one: 0,
    second: 1, '2nd': 1, '2': 1, two: 1,
    third: 2, '3rd': 2, '3': 2, three: 2,
    fourth: 3, '4th': 3, '4': 3, four: 3,
    fifth: 4, '5th': 4, '5': 4, five: 4,
    sixth: 5, '6th': 5, '6': 5, six: 5,
    seventh: 6, '7th': 6, '7': 6, seven: 6,
    eighth: 7, '8th': 7, '8': 7, eight: 7,
    ninth: 8, '9th': 8, '9': 8, nine: 8,
    tenth: 9, '10th': 9, '10': 9, ten: 9,
    last: -1
  };

  const numMap: Record<string, number> = {
    half: 0.5, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10
  };

  const resolveIndex = (str: string, count: number): number | null => {
    const s = str.trim().toLowerCase();
    const idx = wordMap[s] ?? (parseInt(s, 10) - 1);
    if (isNaN(idx)) return null;
    const finalIdx = idx < 0 ? count + idx : idx;
    return (finalIdx >= 0 && finalIdx < count) ? finalIdx : null;
  };

  const parseNum = (str?: string): number | null => {
    if (!str) return null;
    const s = str.trim().toLowerCase();
    return numMap[s] ?? (isNaN(parseFloat(s)) ? null : parseFloat(s));
  };

  const normalizeTransition = (raw: string): any => {
    const s = raw.toLowerCase().replace('-', ' ');
    if (s.includes('crossfade') || s.includes('dissolve')) return 'crossfade';
    if (s.includes('black')) return 'dip_black';
    if (s.includes('white')) return 'dip_white';
    if (s.includes('fade in')) return 'fade_in';
    if (s.includes('fade out')) return 'fade_out';
    if (s.includes('none') || s.includes('cut')) return 'none';
    return 'crossfade';
  };

  const recalcTimeline = () => {
    let cur = 0;
    for (const c of plan.clips) {
      c.start_time = cur;
      cur += c.duration;
    }
    plan.duration_seconds = cur;
  };

  const clipCount = plan.clips.length;

  // 1. Head and Tail Transitions
  if (/fade[- ]?in at (?:the )?(?:beginning|start)/.test(lower)) {
    const dMatch = lower.match(/(\d+(?:\.\d+)?|one|two|three)\s*(?:seconds?|s\b)/);
    const dur = dMatch ? (parseNum(dMatch[1]) || 0.5) : 0.5;
    plan.head_transition = { enabled: true, type: 'fade_in', duration: Math.min(2.0, Math.max(0.2, dur)) };
    changes.push(`Added a ${plan.head_transition.duration}s fade-in at the beginning`);
  }

  if (/fade[- ]?out (?:the video )?at (?:the )?(?:end|finish)/.test(lower)) {
    const dMatch = lower.match(/(\d+(?:\.\d+)?|one|two|three)\s*(?:seconds?|s\b)/);
    const dur = dMatch ? (parseNum(dMatch[1]) || 0.5) : 0.5;
    plan.tail_transition = { enabled: true, type: 'fade_out', duration: Math.min(2.0, Math.max(0.2, dur)) };
    changes.push(`Added a ${plan.tail_transition.duration}s fade-out at the end`);
  }

  // 2. Batch Transitions
  const batchMatch = lower.match(/(?:apply|add|set)\s+(?:a\s+)?(\d+(?:\.\d+)?|one|two|three)?[- ]?(?:second|s)?[- ]?(crossfade|dissolve|dip to black|dip to white|fade in|fade out|fade)\s+(?:transition\s+)?between (?:every|all)(?:\s+adjacent)?\s+(?:photo|clip|image)s?/);
  if (batchMatch && clipCount > 1) {
    const dur = parseNum(batchMatch[1]) || 0.5;
    const tType = normalizeTransition(batchMatch[2]);
    plan.transitions = [];
    for (let i = 0; i < clipCount - 1; i++) {
      plan.clips[i].transition = tType;
      plan.transitions.push({
        id: `trans-${i + 1}`,
        from_clip_id: plan.clips[i].id,
        to_clip_id: plan.clips[i + 1].id,
        type: tType,
        duration: dur,
        enabled: true
      });
    }
    changes.push(`Applied a ${dur}s ${tType.replace('_', ' ')} transition between every adjacent photo`);
  }

  // 3. Specific Transition Between Two Photos
  const specificMatch = lower.match(/(?:add|apply|set|replace)\s+(?:a\s+|the\s+)?(?:(\d+(?:\.\d+)?|one|two|three)?[- ]?(?:seconds?|s)?[- ]?)?(crossfade|dissolve|dip to black|dip to white|fade[- ]?in|fade[- ]?out|fade)?\s*(?:transition\s+)?(?:between|from)\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)\s+(?:and|to)\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)(?:\s+(?:photos?|clips?|images?))?(?:\s+with\s+(?:a\s+)?(crossfade|dissolve|dip to black|dip to white|fade[- ]?in|fade[- ]?out|fade))?/);
  if (specificMatch && clipCount > 1 && !batchMatch) {
    const rawType = specificMatch[5] || specificMatch[2] || 'crossfade';
    const tType = normalizeTransition(rawType);
    const idxA = resolveIndex(specificMatch[3], clipCount);
    const idxB = resolveIndex(specificMatch[4], clipCount);
    if (idxA !== null && idxB !== null) {
      const fromIdx = Math.min(idxA, idxB);
      const toIdx = Math.max(idxA, idxB);
      if (toIdx - fromIdx === 1) {
        const dur = Math.min(2.0, Math.max(0.1, parseNum(specificMatch[1]) || 0.5));
        const cFrom = plan.clips[fromIdx];
        const cTo = plan.clips[toIdx];
        cFrom.transition = tType;
        const existing = plan.transitions.find(t => t.from_clip_id === cFrom.id && t.to_clip_id === cTo.id);
        if (existing) {
          existing.type = tType;
          existing.duration = dur;
          existing.enabled = tType !== 'none';
        } else {
          plan.transitions.push({
            id: `trans-${fromIdx + 1}`,
            from_clip_id: cFrom.id,
            to_clip_id: cTo.id,
            type: tType,
            duration: dur,
            enabled: tType !== 'none'
          });
        }
        changes.push(`Applied a ${dur}s ${tType.replace('_', ' ')} transition between photo ${fromIdx + 1} and photo ${toIdx + 1}`);
      }
    }
  }

  // 4. Remove Transition
  const removeMatch = lower.match(/remove\s+(?:the\s+)?transition\s+between\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)\s+and\s+(?:the\s+)?(?:photos?|clips?|images?)?\s*(\w+)/);
  if (removeMatch && clipCount > 1) {
    const idxA = resolveIndex(removeMatch[1], clipCount);
    const idxB = resolveIndex(removeMatch[2], clipCount);
    if (idxA !== null && idxB !== null) {
      const fromIdx = Math.min(idxA, idxB);
      const toIdx = Math.max(idxA, idxB);
      const cFrom = plan.clips[fromIdx];
      const cTo = plan.clips[toIdx];
      cFrom.transition = 'none';
      const existing = plan.transitions.find(t => t.from_clip_id === cFrom.id && t.to_clip_id === cTo.id);
      if (existing) {
        existing.type = 'none';
        existing.enabled = false;
      }
      changes.push(`Removed transition between photo ${fromIdx + 1} and photo ${toIdx + 1}`);
    }
  }

  // 5. Remove a Specific Photo
  const removeClipMatch = lower.match(/(?:remove|delete|drop)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)(?:\s+from\s+(?:the\s+)?timeline)?/);
  if (removeClipMatch && clipCount > 0) {
    const idx = resolveIndex(removeClipMatch[1], clipCount);
    if (idx !== null) {
      const [removedClip] = plan.clips.splice(idx, 1);
      plan.transitions = plan.transitions.filter(
        t => t.from_clip_id !== removedClip.id && t.to_clip_id !== removedClip.id
      );
      recalcTimeline();
      changes.push(`Removed photo ${idx + 1} from the timeline`);
    }
  }

  // 6. Extend or Shorten Photo
  const extMatch = lower.match(/(?:extend|lengthen|increase)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+by\s+(\d+(?:\.\d+)?|one|two|three|four|five)\s*(?:seconds?|secs?|s\b)?/);
  if (extMatch && clipCount > 0) {
    const idx = resolveIndex(extMatch[1], clipCount);
    const delta = parseNum(extMatch[2]);
    if (idx !== null && delta) {
      plan.clips[idx].duration = Math.round((plan.clips[idx].duration + delta) * 100) / 100;
      recalcTimeline();
      changes.push(`Extended photo ${idx + 1} by ${delta}s (new duration: ${plan.clips[idx].duration}s)`);
    }
  }

  // 6. Set Photo Duration
  const clipMatch = lower.match(/(?:make|set)\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+(?:last|to|duration)?\s*(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:seconds?|secs?|s\b)?/);
  if (clipMatch && !specificMatch && !extMatch && clipCount > 0) {
    const idx = resolveIndex(clipMatch[1], clipCount);
    const dur = parseNum(clipMatch[2]);
    if (idx !== null && dur && dur >= 0.5) {
      plan.clips[idx].duration = dur;
      recalcTimeline();
      changes.push(`Set photo ${idx + 1} duration to ${dur}s`);
    }
  }

  // 7. Move Photo
  const moveMatch = lower.match(/move\s+(?:the\s+)?(\w+)\s+(?:photo|clip|image)\s+to\s+(?:the\s+)?(beginning|start|end|front|back|position\s+\d+|photo\s+\d+)/);
  if (moveMatch && clipCount > 1) {
    const srcIdx = resolveIndex(moveMatch[1], clipCount);
    const destWord = moveMatch[2];
    let destIdx: number | null = null;
    if (destWord === 'beginning' || destWord === 'start' || destWord === 'front') destIdx = 0;
    else if (destWord === 'end' || destWord === 'back') destIdx = clipCount - 1;
    else {
      const numM = destWord.match(/\d+/);
      if (numM) destIdx = parseInt(numM[0], 10) - 1;
    }
    if (srcIdx !== null && destIdx !== null && destIdx >= 0 && destIdx < clipCount && srcIdx !== destIdx) {
      const [moved] = plan.clips.splice(srcIdx, 1);
      plan.clips.splice(destIdx, 0, moved);

      // Rebuild adjacent transitions safely to align with new sequence
      const newTransitions: TransitionConfig[] = [];
      for (let i = 0; i < plan.clips.length - 1; i++) {
        const c1 = plan.clips[i];
        const c2 = plan.clips[i + 1];
        const existing = (plan.transitions || []).find(t => t.from_clip_id === c1.id && t.to_clip_id === c2.id);
        if (existing) {
          newTransitions.push(existing);
        } else {
          newTransitions.push({
            id: `trans-${c1.id}-${c2.id}`,
            from_clip_id: c1.id,
            to_clip_id: c2.id,
            type: (c1.transition || 'none') as any,
            duration: 0.5,
            enabled: c1.transition !== 'none'
          });
        }
      }
      plan.transitions = newTransitions;

      recalcTimeline();
      changes.push(`Moved photo ${srcIdx + 1} to ${destIdx === 0 ? 'beginning' : destIdx === clipCount - 1 ? 'end' : `position ${destIdx + 1}`}`);
    }
  }

  // 8. Aspect Ratio & Fit Mode
  if (lower.includes('landscape') || lower.includes('16:9') || lower.includes('horizontal')) {
    plan.aspect_ratio = '16:9';
    changes.push('Set aspect ratio to landscape (16:9)');
  } else if (lower.includes('square') || lower.includes('1:1')) {
    plan.aspect_ratio = '1:1';
    changes.push('Set aspect ratio to square (1:1)');
  } else if (lower.includes('portrait') || lower.includes('9:16') || lower.includes('vertical')) {
    plan.aspect_ratio = '9:16';
    changes.push('Set aspect ratio to portrait (9:16)');
  }

  if (lower.includes('fit mode to fit') || lower.includes('letterbox') || lower.includes('pillarbox')) {
    plan.fit_mode = 'fit';
    changes.push('Set fit mode to Fit (preserve entire image)');
  } else if (lower.includes('fit mode to fill') || lower.includes('crop to fill') || lower.includes('fill mode')) {
    plan.fit_mode = 'fill';
    changes.push('Set fit mode to Fill (crop to fill)');
  }

  // 9. Style & Title Presets
  const titleMatch = text.match(/(?:change\s+(?:the\s+)?title\s+to|set\s+(?:the\s+)?title\s+to|title\s+to|name\s+it\s+to)\s*["']?([^"'.\n]+)["']?/i);
  if (titleMatch) {
    plan.title.enabled = true;
    plan.title.text = titleMatch[1].trim();
    changes.push(`Updated title to: '${plan.title.text}'`);
  } else if (lower.includes('add a title at the beginning') || lower.includes('add title')) {
    plan.title.enabled = true;
    changes.push('Enabled title overlay at the beginning');
  }

  if (lower.includes('noir') || lower.includes('monochrome')) {
    plan.style = 'noir';
    changes.push('Selected Film Noir style');
  } else if (lower.includes('vintage') || lower.includes('retro')) {
    plan.style = 'vintage';
    changes.push('Selected Vintage style');
  } else if (lower.includes('minimal')) {
    plan.style = 'minimal';
    changes.push('Selected Minimal style');
  } else if (lower.includes('cinematic')) {
    plan.style = 'cinematic';
    changes.push('Selected Cinematic style');
  }

  const explanation = changes.length > 0
    ? `RayFlow applied: ${changes.join(', ')}.`
    : `Could not recognize command '${text}'. Try 'Apply a crossfade between photos 1 and 2', 'Add a fade-in at the beginning', 'Change the video to landscape', or 'Make the first photo last 3 seconds'.`;

  return {
    plan,
    explanation,
    applied_changes: changes
  };
}

export async function interpretNaturalCommand(
  command: string,
  currentPlan?: EditingPlan
): Promise<CommandResponse> {
  try {
    const res = await fetch(`${API_BASE}/commands/interpret`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command,
        current_plan: currentPlan,
      }),
    });

    if (res.ok) {
      return await res.json();
    }

  } catch (err) {
    console.warn('Backend interpret endpoint unavailable, using local parser:', err);
  }

  // Fallback to local parser
  return localInterpretCommand(command, currentPlan);
}

export async function createDirectorPlan(command: string, currentPlan: EditingPlan, context?: import('../types').DirectorContext, conversation?: import('../types').DirectorTurn[]): Promise<AIEditingPlan> {
  const res = await fetch(`${API_BASE}/ai/plan`, {
    method: 'POST',
    credentials: 'include',
    signal: AbortSignal.timeout(610000),
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, current_plan: currentPlan, context, conversation }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The AI planning request failed.');
  return body;
}

export async function applyDirectorPlan(aiPlan: AIEditingPlan, currentPlan: EditingPlan): Promise<AIEditingPlan> {
  const res = await fetch(`${API_BASE}/ai/apply`, {
    method: 'POST',
    credentials: 'include',
    signal: AbortSignal.timeout(180000),
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ai_plan: { explanation: aiPlan.explanation, actions: aiPlan.actions, clarification: aiPlan.clarification }, current_plan: currentPlan }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The approved edit could not be applied.');
  return body;
}

// Keep existing integrations compatible while all providers share one Director transport.
export const createOpenRouterPlan = createDirectorPlan;
export const applyOpenRouterPlan = applyDirectorPlan;

export async function generateProjectPlan(
  plan: EditingPlan,
  imageFilenames: string[],
  audioFilename?: string
): Promise<EditingPlan> {
  const res = await fetch(`${API_BASE}/projects/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      plan,
      image_filenames: imageFilenames,
      audio_filename: audioFilename,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Plan generation failed' }));
    throw new Error(err.detail || 'Plan generation failed');
  }

  return await res.json();
}

export async function startRender(
  plan: EditingPlan,
  imageFilenames: string[],
  audioFilename?: string
): Promise<string> {
  const res = await fetch(`${API_BASE}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      plan,
      image_filenames: imageFilenames,
      audio_filename: audioFilename,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start video rendering' }));
    throw new Error(err.detail || 'Failed to start video rendering');
  }

  const data = await res.json();
  return data.job_id;
}

export async function getRenderProgress(jobId: string): Promise<RenderJobStatus> {
  const res = await fetch(`${API_BASE}/render/${jobId}`);
  if (!res.ok) {
    throw new Error('Failed to fetch render job status');
  }
  return await res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/render/${jobId}/download`;
}

export function getMediaUrl(relativeUrl: string): string {
  if (relativeUrl.startsWith('http://') || relativeUrl.startsWith('https://')) {
    return relativeUrl;
  }
  return relativeUrl.startsWith('/')
    ? `${API_ORIGIN}${relativeUrl}`
    : `${API_BASE}/uploads/${encodeURIComponent(relativeUrl)}`;
}

export async function startTranscription(
  mediaFilename: string,
  modelSize?: string,
  language?: string,
): Promise<string> {
  const res = await fetch(`${API_BASE}/transcribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      media_filename: mediaFilename,
      model_size: modelSize,
      language: language || undefined,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start transcription' }));
    throw new Error(err.detail || 'Failed to start transcription');
  }

  const data = await res.json();
  return data.job_id;
}

export async function getTranscriptionStatus(jobId: string): Promise<TranscriptionJob> {
  const res = await fetch(`${API_BASE}/transcribe/${jobId}`);
  if (!res.ok) {
    throw new Error('Failed to fetch transcription status');
  }
  return await res.json();
}

export async function downloadCaptions(plan: EditingPlan, format: CaptionFormat): Promise<void> {
  const res = await fetch(`${API_BASE}/captions/export/${format}?aspect_ratio=${encodeURIComponent(plan.aspect_ratio)}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({duration_seconds: plan.duration_seconds, subtitles: plan.subtitles || []}),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    const detail = typeof error.detail === 'string' ? error.detail : error.detail?.[0]?.msg;
    throw new Error(detail || 'Caption export failed. Check caption text and timestamps.');
  }
  const url = URL.createObjectURL(await res.blob());
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `rayflow-captions.${format}`;
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function checkOllamaStatus(host?: string): Promise<{ available: boolean; ready?: boolean; host: string; models: string[]; default_model?: string; error?: string }> {
  try {
    const url = host ? `${API_BASE}/ollama/status?host=${encodeURIComponent(host)}` : `${API_BASE}/ollama/status`;
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error('Ollama status request failed.');
    return await res.json();
  } catch {
    return { available: false, host: host || '', models: [], error: 'The backend could not check Ollama. Check the backend connection and retry.' };
  }
}

export async function interpretWithOllama(
  command: string,
  plan: EditingPlan,
  model?: string,
  host?: string
): Promise<CommandResponse> {
  const res = await fetch(`${API_BASE}/ollama/interpret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, plan, model, host }),
    signal: AbortSignal.timeout(615000),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to interpret with Ollama' }));
    throw new Error(err.detail || 'Failed to interpret with Ollama');
  }
  return await res.json();
}

export async function suggestVisualInserts(
  subtitles: any[],
  availableAssets: any[],
  defaultMode: string = 'pip'
): Promise<any[]> {
  const res = await fetch(`${API_BASE}/inserts/suggest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      subtitles,
      available_assets: availableAssets,
      default_mode: defaultMode,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to suggest visual inserts' }));
    throw new Error(err.detail || 'Failed to suggest visual inserts');
  }
  return await res.json();
}

export async function generateAutoEditReel(
  mediaFilename: string,
  styleKey: string = 'fitness_energy',
  availableAssets?: any[],
  whisperModel: string = 'tiny',
  aspectRatio: EditingPlan['aspect_ratio'] = '9:16',
  includeCaptions: boolean = true,
  currentPlan?: EditingPlan,
  onStage?: (stage: string) => void,
  tightenSpeech: boolean = false
): Promise<EditingPlan> {
  const res = await fetch(`${API_BASE}/auto-edit/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      media_filename: mediaFilename,
      style_key: styleKey,
      available_assets: availableAssets,
      whisper_model: whisperModel,
      aspect_ratio: aspectRatio,
      include_captions: includeCaptions,
      current_plan: currentPlan,
      auto_broll: currentPlan?.auto_broll !== false,
      list_sounds: currentPlan?.list_sounds !== false,
      tighten_speech: tightenSpeech,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Auto-edit workflow failed' }));
    throw new Error(err.detail || 'Auto-edit workflow failed');
  }
  const job = await res.json();
  return await waitCreativeJob<EditingPlan>(job.job_id, onStage);
}

export async function creativeRequest<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body), signal});
  if(!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : error.detail?.[0]?.msg || 'The request could not be completed.');
  }
  return response.json();
}

export async function waitCreativeJob<T>(jobId: string, onStage?: (stage: string) => void): Promise<T> {
  for (;;) {
    const job = await creativeRequest<{status:string; stage:string; result:T; error?:string}>(`/creative/jobs/${jobId}`);
    onStage?.(job.stage);
    if(job.status === 'completed') return job.result;
    if(job.status === 'failed') throw new Error(job.error || 'Local processing failed.');
    if(job.status === 'cancelled') throw new Error('Local processing cancelled.');
    await new Promise(resolve => setTimeout(resolve, 700));
  }
}
