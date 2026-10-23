import { getEditorProviders, getWorkspaceSession, saveWorkspacePreferences } from '../../../services/editorClient';

const providerId = (name: string) => ({ unsplash_access_key: 'unsplash', sketchfab_api_token: 'sketchfab' }[name] || name.replace(/_api_key$/, ''));
const isCredential = (key: string) => /(?:api[_-]?key|api[_-]?token|access[_-]?(?:token|key)|refresh[_-]?token|cloud_.*auth|^hfToken$|client[_-]?secret|^password$)/i.test(key);
let timer: ReturnType<typeof setTimeout> | undefined;
const cache = new Map<string, string>();
let cacheOwner: string | undefined;
let pending: Record<string, string | null> = {};
function scope() {
  const identity = getWorkspaceSession()?.workspace_id || 'offline';
  if (identity !== cacheOwner) { cache.clear(); pending = {}; clearTimeout(timer); cacheOwner = identity; }
  return identity;
}
function schedule(key: string, value: string | null) {
  const identity = scope(); pending[key] = value;
  clearTimeout(timer);
  timer = setTimeout(() => {
    if (identity !== getWorkspaceSession()?.workspace_id) return;
    const patch = pending; pending = {};
    void saveWorkspacePreferences({ editor: patch }).catch(error => {
      pending = { ...patch, ...pending };
      window.dispatchEvent(new CustomEvent('rayflow:save-error', { detail: String(error.message) }));
    });
  }, 800);
}
function inspect(value: unknown) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (isCredential(key) && typeof child === 'string' && child && child !== 'rayflow-managed:configured') throw new Error('Store credentials in Rayflow Connections.');
    inspect(child);
  }
}

/** Only nonsecret preferences are cached. A configured marker is never a key. */
export const editorStorage = {
  getItem(key: string): string | null {
    if (isCredential(key)) {
      return getEditorProviders().some(provider => provider.id === providerId(key) && provider.configured) ? 'rayflow-managed:configured' : null;
    }
    const session = getWorkspaceSession();
    scope();
    if (cache.has(key)) return cache.get(key)!;
    const saved = session?.preferences?.editor?.[key];
    if (typeof saved === 'string') return saved;
    return typeof localStorage === 'undefined' ? null : localStorage.getItem(`rayflow:${session?.workspace_id || 'offline'}:editor:${key}`);
  },
  setItem(key: string, value: string) {
    if (isCredential(key)) throw new Error('Save provider credentials in Rayflow Connections.');
    let decoded: unknown;
    try { decoded = JSON.parse(value); } catch { /* ordinary string preference */ }
    inspect(decoded);
    scope();
    const session = getWorkspaceSession();
    cache.set(key, String(value));
    window.localStorage.setItem(`rayflow:${session?.workspace_id || 'offline'}:editor:${key}`, String(value));
    schedule(key, String(value));
  },
  removeItem(key: string) {
    if (isCredential(key)) throw new Error('Remove credentials in Rayflow Connections.');
    scope();
    cache.delete(key);
    const session = getWorkspaceSession();
    if (session?.preferences?.editor) delete session.preferences.editor[key];
    window.localStorage.removeItem(`rayflow:${session?.workspace_id || 'offline'}:editor:${key}`);
    schedule(key, null);
  },
};
