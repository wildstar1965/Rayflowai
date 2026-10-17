import {
  EditingPlan,
  AudioAnalysisResult,
  UploadedImage,
  UploadedAudio,
  CommandResponse,
  RenderJobStatus,
} from '../types';

const API_BASE = 'http://localhost:8000/api';

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function uploadImages(files: File[]): Promise<UploadedImage[]> {
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

export async function interpretNaturalCommand(
  command: string,
  currentPlan?: EditingPlan
): Promise<CommandResponse> {
  const res = await fetch(`${API_BASE}/commands/interpret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      command,
      current_plan: currentPlan,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Command interpretation failed' }));
    throw new Error(err.detail || 'Command interpretation failed');
  }

  return await res.json();
}

export async function generateProjectPlan(
  plan: EditingPlan,
  imageFilenames: string[],
  audioFilename?: string
): Promise<EditingPlan> {
  const url = new URL(`${API_BASE}/projects/plan`);
  imageFilenames.forEach(img => url.searchParams.append('image_filenames', img));
  if (audioFilename) {
    url.searchParams.append('audio_filename', audioFilename);
  }

  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(plan),
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
  return `http://localhost:8000${relativeUrl}`;
}
