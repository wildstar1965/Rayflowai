export interface EditorProvider { id: string; label: string; configured: boolean; tested?: boolean; can_test?: boolean; model?: string; hosts: string[]; local?: boolean; base_url?: string }
export interface WorkspaceSession { workspace_id: string; guest: boolean; storage: 'local' | 'supabase'; preferences: Record<string, any> }
export interface EditorProject { id: string; name: string; revision: number; document_revision?: number; version: number; kind: string; project: Record<string, any>; files?: string[]; read_only?: boolean }
const base = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
let session: WorkspaceSession | null = null;
let providers: EditorProvider[] = [];
let initializePromise: Promise<WorkspaceSession> | null = null;
let preferenceQueue: Promise<void> = Promise.resolve();

class EditorRequestError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

export async function editorRequest<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  // Bound metadata/initialization requests; large media uploads keep their
  // caller-controlled lifetime rather than inheriting the startup deadline.
  const response = await fetch(`${base}${path}`, { credentials: 'include', signal: init.body instanceof FormData ? undefined : AbortSignal.timeout(30000), ...init,
    headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init.headers } });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new EditorRequestError(typeof value?.detail === 'string' ? value.detail : `Request failed (HTTP ${response.status}).`, response.status);
  if (value === null) throw new Error('The backend returned an invalid response.');
  return value as T;
}

export function getWorkspaceSession() { return session; }
export function getEditorProviders() { return providers; }
export async function refreshEditorProviders() {
  providers = (await editorRequest<{ providers: EditorProvider[] }>('/editor/providers')).providers;
  window.dispatchEvent(new Event('rayflow:providers'));
  return providers;
}
export async function initializeWorkspace(): Promise<WorkspaceSession> {
  if (session) return session;
  if (!initializePromise) initializePromise = (async () => {
    session = await editorRequest<WorkspaceSession>('/session', { method: 'POST' });
    await refreshEditorProviders();
    return session;
  })().catch(error => { initializePromise = null; session = null; throw error; });
  return initializePromise;
}
export function saveWorkspacePreferences(patch: Record<string, any>) {
  const body = JSON.stringify(patch);
  const task = preferenceQueue.catch(() => undefined).then(async () => {
    if (!session) await initializeWorkspace();
    session!.preferences = await editorRequest('/editor/preferences', { method: 'PATCH', body });
    window.dispatchEvent(new Event('rayflow:preferences'));
  });
  preferenceQueue = task;
  return task;
}
export async function saveEditorProvider(id: string, key?: string, model?: string) {
  await editorRequest(`/editor/providers/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ key, model }) });
  return refreshEditorProviders();
}
export async function deleteEditorProvider(id: string) {
  await editorRequest(`/editor/providers/${encodeURIComponent(id)}`, { method: 'DELETE' });
  return refreshEditorProviders();
}

export async function runEditorJob(kind: string, payload: any, signal?: AbortSignal, progress?: (value: number) => void) {
  if (signal?.aborted) throw new DOMException('Operation cancelled', 'AbortError');
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify([kind, payload])))))
    .map(byte => byte.toString(16).padStart(2, '0')).join('');
  // Persist only an opaque submission key and request hash, never prompts or credentials.
  const storageKey = `rayflow:${session?.workspace_id}:pending:${digest}`;
  let submission = crypto.randomUUID() as string;
  try { submission = sessionStorage.getItem(storageKey) || submission; sessionStorage.setItem(storageKey, submission); } catch { /* private browsing */ }
  const body = JSON.stringify({ kind, payload, submission_key: submission });
  let job: any;
  for (let attempt = 0; attempt < 3; attempt++) {
    try { job = await editorRequest('/editor/jobs', { method: 'POST', body }); break; }
    catch (error) {
      if (error instanceof EditorRequestError && error.status < 500) {
        try { sessionStorage.removeItem(storageKey); } catch { /* unavailable storage */ }
        throw error;
      }
      if (attempt === 2) throw new Error('The job submission could not be confirmed. Retry this action to check the same submission safely.');
      await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
    }
  }
  const cancel = () => {
    void editorRequest(`/editor/jobs/${job.id}/cancel`, { method: 'POST' }).catch(() => undefined);
    // Local rendering can be started afresh after cancelling; retain ambiguous
    // paid submissions so a retry cannot create a second provider generation.
    if (['export', 'audio-mastering', 'audio-remaster', 'surface-map', 'corridor-key'].includes(kind)) {
      try { sessionStorage.removeItem(storageKey); } catch { /* unavailable storage */ }
    }
  };
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) cancel();
  const deadline = Date.now() + 30 * 60 * 1000;
  try {
    for (;;) {
      if (signal?.aborted) throw new DOMException('Operation cancelled', 'AbortError');
      const current = await editorRequest(`/editor/jobs/${job.id}`);
      progress?.(current.progress || 0);
      if (current.status === 'completed') {
        try { sessionStorage.removeItem(storageKey); } catch { /* unavailable storage */ }
        return current.result;
      }
      if (['failed', 'cancelled', 'interrupted'].includes(current.status)) {
        if (!['provider', 'gemini'].includes(kind) && current.status !== 'interrupted') try { sessionStorage.removeItem(storageKey); } catch { /* unavailable storage */ }
        throw new Error(current.error || `Operation ${current.status}.`);
      }
      if (Date.now() > deadline) throw new Error('This job is taking longer than expected. Its submission is preserved; check its status in Dashboard.');
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
  } finally { signal?.removeEventListener('abort', cancel); }
}

export const editorFileUrl = (path: string) => `${base}/editor/assets/file/${path.split('/').map(encodeURIComponent).join('/')}`;
export async function uploadEditorAsset(file: File, signal?: AbortSignal) {
  signal?.throwIfAborted();
  await initializeWorkspace();
  signal?.throwIfAborted();
  if (session?.storage === 'supabase') {
    const ticket = await editorRequest('/editor/assets/upload-ticket', { method: 'POST', body: JSON.stringify({ name: file.name, type: file.type, size: file.size }), signal });
    if (!ticket.upload?.url) throw new Error('The private upload endpoint is unavailable.');
    const response = await fetch(ticket.upload.url, { method: 'PUT', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' }, signal });
    if (!response.ok) throw new Error('Media upload failed. Retry the upload.');
    return editorRequest(`/editor/assets/${ticket.asset.id}/complete`, { method: 'POST', signal });
  }
  const form = new FormData(); form.append('file', file);
  return editorRequest('/editor/assets', { method: 'POST', body: form, signal });
}
