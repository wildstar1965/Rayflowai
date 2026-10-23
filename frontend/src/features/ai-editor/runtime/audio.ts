import { editorRequest, runEditorJob, uploadEditorAsset } from '../../../services/editorClient';

export async function audioStatus(kind: 'audio-mastering' | 'audio-remaster') {
  const capabilities = await editorRequest('/editor/capabilities');
  return capabilities.processors[kind];
}

async function uploadAudio(value: { base64: string; mimeType: string; name?: string }) {
  const bytes = Uint8Array.from(atob(value.base64.replace(/^data:[^,]+,/, '')), ch => ch.charCodeAt(0));
  const asset = await uploadEditorAsset(new File([bytes], value.name || 'audio.wav', { type: value.mimeType }));
  return asset.url as string;
}

export async function processAudio(kind: 'audio-mastering' | 'audio-remaster', request: any) {
  const { target, reference, projectPath: _projectPath, ...options } = request;
  if (!target) throw new Error('Select source audio before processing.');
  const targetPath = await uploadAudio(target);
  const referencePath = reference ? await uploadAudio(reference) : undefined;
  const result = await runEditorJob(kind, { ...options, targetPath, referencePath });
  return { ...result, ok: true, outputName: request.outputName || 'Rayflow master.wav' };
}

export async function operatorAudioSetup(kind: 'audio-mastering' | 'audio-remaster') {
  const status = await audioStatus(kind);
  if (!status.ready) throw new Error(status.error || 'The backend operator must install the audio processor dependencies.');
  return status;
}
