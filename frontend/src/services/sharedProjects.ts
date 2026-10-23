import { editorRequest, getWorkspaceSession, saveWorkspacePreferences, type EditorProject } from './editorClient';

export interface ProjectSequence {
  id: string; kind: 'rayflow' | 'editor'; name: string; revision: number; document: Record<string, any>;
}
export type SharedProject = EditorProject & { sequences: ProjectSequence[]; assets: string[]; production: Record<string, any> };
export const LEGACY_REEL_KEY = 'rayflow_project_state_v3';
let activePromise: Promise<SharedProject> | undefined;

export async function ensureActiveProject(): Promise<SharedProject> {
  if (activePromise) return activePromise;
  activePromise = (async () => {
    const session = getWorkspaceSession();
    if (!session) throw new Error('Connect to your workspace before saving.');
    if (session.preferences.activeProject) return editorRequest<SharedProject>(`/editor/projects/${session.preferences.activeProject}`);
    let legacy: Record<string, any> | undefined;
    if (!session.preferences.legacyReelImported && !localStorage.getItem('rayflow_legacy_reel_migrated')) {
      try { legacy = JSON.parse(localStorage.getItem(LEGACY_REEL_KEY) || 'null') || undefined; } catch { /* retain unparseable originals */ }
    }
    const project = await editorRequest<SharedProject>('/editor/projects', { method: 'POST', body: JSON.stringify({
      name: legacy?.projectName || 'My Rayflow project', project: {}, kind: 'editor',
    }) });
    if (legacy) {
      const sequence = await saveReelSequence(project.id, legacy, 0);
      project.sequences = [sequence];
      localStorage.setItem('rayflow_legacy_reel_migrated', 'true');
    }
    // The original browser key is intentionally retained for recovery.
    await saveWorkspacePreferences({ activeProject: project.id, legacyReelImported: Boolean(legacy) });
    return project;
  })();
  try { return await activePromise; } finally { activePromise = undefined; }
}

export function saveReelSequence(project: string, document: Record<string, any>, revision: number) {
  return editorRequest<ProjectSequence>(`/editor/projects/${project}/sequences/reel-primary`, {
    method: 'PUT', body: JSON.stringify({ kind: 'rayflow', name: document.projectName || 'Rayflow reel', document, revision }),
  });
}
