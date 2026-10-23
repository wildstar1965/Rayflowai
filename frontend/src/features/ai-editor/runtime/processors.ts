import { editorRequest, runEditorJob } from '../../../services/editorClient';
export async function processorStatus(kind: 'surface-map' | 'corridor-key') {
  return (await editorRequest('/editor/capabilities')).processors[kind];
}
export async function setupProcessor(kind: 'surface-map' | 'corridor-key') {
  const status = await processorStatus(kind);
  if (!status.ready) throw new Error(status.error || 'The backend operator must configure this processor.');
  return status;
}
export function runProcessor(kind: 'surface-map' | 'corridor-key', request: any) {
  const { repoPath: _repoPath, projectPath: _projectPath, ...payload } = request;
  return runEditorJob(kind, payload);
}
