import type { ElectronProjectApi } from '../types';
import { editorRequest, editorFileUrl, runEditorJob, getWorkspaceSession, uploadEditorAsset, type EditorProject } from '../../../services/editorClient';
import { decodeProjectValue, encodeProjectValue, replaceProjectReferences } from './serialization';
import { mergeProjectDocuments } from './projectMerge';

const revisions = new Map<string, number>();
const localBaselines = new Map<string, any>();
const savedBaselines = new Map<string, any>();
const readOnly = new Set<string>();
export const isProjectReadOnly = (id?: string | null) => Boolean(id && readOnly.has(id.split('/')[0]));
const saves = new Map<string, Promise<unknown>>();
async function serializeSave<T>(identity: string, operation: () => Promise<T>): Promise<T> {
  const pending = (saves.get(identity) || Promise.resolve()).catch(() => undefined).then(operation);
  saves.set(identity, pending);
  try { return await pending; } finally { if (saves.get(identity) === pending) saves.delete(identity); }
}
let exportProgress: ((progress: any) => void) | undefined;
export function projectFileUrl(project: string, relative: string) {
  if (relative.startsWith('/api/editor/') || relative.startsWith('/api/uploads/')) return relative;
  return `/api/editor/projects/${encodeURIComponent(project.split('/')[0])}/files/${relative.split('/').map(encodeURIComponent).join('/')}`;
}
export function chooseProject(): Promise<string | null> {
  return new Promise(resolve => window.dispatchEvent(new CustomEvent('rayflow:choose-project', { detail: { resolve } })));
}
async function record(id: string, rememberRevision = false) {
  const project = await editorRequest<EditorProject>(`/editor/projects/${encodeURIComponent(id.split('/')[0])}`);
  if (project.read_only) readOnly.add(project.id); else readOnly.delete(project.id);
  if (rememberRevision) {
    revisions.set(project.id, project.document_revision || 1);
    localBaselines.set(project.id, project.project);
    savedBaselines.set(project.id, project.project);
  }
  return project;
}
async function bytes(url: string): Promise<Uint8Array> {
  const response = await fetch(url, { credentials: 'include' });
  if (!response.ok) throw new Error('Project asset is missing. Import or relink its media.');
  return new Uint8Array(await response.arrayBuffer());
}

export const projectApi: ElectronProjectApi = {
  selectFolder: chooseProject,
  selectFile: chooseProject,
  probeFolder: async ({ folderPath }) => ({ exists: Object.keys((await record(folderPath)).project).length > 0 }),
  initFolder: async ({ folderPath }) => { await record(folderPath); return { ok: true }; },
  saveProject: async ({ folderPath, project, assets }) => {
    const identity = folderPath.split('/')[0];
    return serializeSave(identity, async () => {
    if (!revisions.has(identity)) await record(identity, true);
    if (isProjectReadOnly(identity)) throw new Error('This team project has viewer access. Download and import a copy to edit it.');
    const replacements = new Map<string, string>();
    for (const asset of assets || []) {
      const content = typeof asset.data === 'string' ? asset.data : asset.data instanceof ArrayBuffer ? asset.data : new Uint8Array(asset.data).buffer;
      const bytes = typeof content === 'string' ? new TextEncoder().encode(content) : content;
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map(byte => byte.toString(16).padStart(2, '0')).join('');
      const immutablePath = `objects/${digest}/${asset.relativePath.split('/').pop()}`;
      replacements.set(asset.relativePath, immutablePath);
      if (getWorkspaceSession()?.storage === 'supabase') {
        const ticket = await editorRequest(`/editor/projects/${identity}/file-ticket`, { method: 'POST', body: JSON.stringify({ relativePath: immutablePath }) });
        const response = await fetch(ticket.url, { method: 'PUT', body: content });
        if (!response.ok) throw new Error('Could not upload project media. Your project remains open; retry saving.');
        await editorRequest(`/editor/projects/${identity}/file-complete`, { method: 'POST', body: JSON.stringify({ relativePath: immutablePath }) });
      } else {
        const response = await fetch(projectFileUrl(identity, immutablePath), { method: 'PUT', credentials: 'include', body: content });
        if (!response.ok) throw new Error('Could not save project media. Your project remains open; retry saving.');
      }
    }
    const local = replaceProjectReferences(encodeProjectValue(project), replacements);
    const baseline = localBaselines.get(identity);
    let candidate = mergeProjectDocuments(baseline, local, savedBaselines.get(identity));
    let revision = revisions.get(identity);
    let saved: EditorProject | undefined;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        saved = await editorRequest<EditorProject>(`/editor/projects/${identity}`, { method: 'PUT',
          body: JSON.stringify({ name: candidate.name || project.name || 'Untitled project', project: candidate, kind: 'editor', document_revision: revision }) });
        break;
      } catch (error) {
        if ((error as { status?: number }).status !== 409 || attempt === 2) throw error;
        const current = await record(identity);
        candidate = mergeProjectDocuments(baseline, local, current.project);
        revision = current.document_revision || 1;
      }
    }
    if (!saved) throw new Error('The project is changing in another session. Retry saving.');
    revisions.set(identity, saved.document_revision || 1);
    localBaselines.set(identity, local);
    savedBaselines.set(identity, saved.project);
    window.dispatchEvent(new CustomEvent('rayflow:project-saved', { detail: saved }));
    return { ok: true };
    });
  },
  loadProject: async ({ folderPath }) => { const item = await record(folderPath, true); return { project: { ...decodeProjectValue(item.project), name: item.name } }; },
  statProject: async ({ folderPath }) => { const item = await record(folderPath); return { exists: true, mtimeMs: (item as any).updated * 1000, size: JSON.stringify(item.project).length }; },
  statProjectPath: async ({ folderPath, relativePath }) => { const item = await record(folderPath); return { exists: (item.files || []).includes(relativePath) }; },
  readProjectFile: async ({ folderPath, relativePath }) => {
    if (relativePath === 'project.json') return new TextEncoder().encode(JSON.stringify((await record(folderPath)).project));
    const response = await fetch(projectFileUrl(folderPath, relativePath), { credentials: 'include' });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error('Could not read the project file.');
    return new Uint8Array(await response.arrayBuffer());
  },
  writeProjectFile: async ({ folderPath, relativePath, data, encoding }) => {
    const body = encoding === 'base64' ? Uint8Array.from(atob(data), c => c.charCodeAt(0)) : data;
    if (relativePath === 'project.json') {
      const document = JSON.parse(typeof body === 'string' ? body : new TextDecoder().decode(body));
      if (!document || typeof document !== 'object' || Array.isArray(document)) throw new Error('The cloud project must contain a project object.');
      // Cloud pull/merge must update the authoritative document, not a shadow blob.
      await projectApi.saveProject({ folderPath, project: document, assets: [] });
      return { ok: true };
    }
    const response = await fetch(projectFileUrl(folderPath, relativePath), { method: 'PUT', credentials: 'include', body });
    if (!response.ok) throw new Error('Could not save the project file.');
    return { ok: true };
  },
  deleteProjectFile: async ({ folderPath, relativePath }) => editorRequest(`/editor/projects/${folderPath}/files/${relativePath}`, { method: 'DELETE' }),
  readFile: async ({ filePath }) => bytes(filePath.startsWith('/api/') ? filePath : editorFileUrl(filePath)),
  openFolder: async ({ folderPath }) => {
    window.dispatchEvent(new CustomEvent('rayflow:project-files', { detail: folderPath.split('/')[0] }));
    return { ok: true, error: null };
  },
  listSystemFonts: async () => ({ fonts: ['Onest', 'Arial', 'Georgia', 'Courier New', 'Times New Roman'] }),
  exportVideo: async (payload, signal) => {
    const used = new Set(payload.project.timelineClips.map((clip: any) => clip.mediaId));
    const uploaded = new Map<string, string>();
    const mediaItems = [];
    for (const item of payload.project.mediaItems) {
      signal?.throwIfAborted();
      if (!used.has(item.id)) continue;
      if (!/^(blob:|data:)/.test(item.url || '')) { mediaItems.push(item); continue; }
      exportProgress?.({ percent: 0, stage: 'Preparing media' });
      if (!uploaded.has(item.url)) {
        const response = await fetch(item.url, { signal });
        if (!response.ok) throw new Error('This generated asset is no longer available. Recreate or relink it before exporting.');
        const blob = await response.blob();
        const asset = await uploadEditorAsset(new File([blob], item.name || 'export-media', { type: blob.type || 'application/octet-stream' }), signal);
        uploaded.set(item.url, asset.url);
      }
      mediaItems.push({ ...item, url: uploaded.get(item.url), sourceUrl: uploaded.get(item.url) });
    }
    const result = await runEditorJob('export', { ...payload, project: { ...payload.project, mediaItems } }, signal,
      percent => exportProgress?.({ percent, stage: 'render' }));
    return { ok: true, outputPath: result.url };
  },
  exportStoryboardPdf: async ({ html }) => {
    const popup = window.open('', '_blank');
    if (!popup) throw new Error('Allow the print window to export a storyboard PDF.');
    popup.document.write(html); popup.document.close();
    popup.onload = () => popup.print();
    return { ok: true };
  },
  onExportProgress: callback => { exportProgress = callback; },
  removeExportProgressListener: () => { exportProgress = undefined; },
};
