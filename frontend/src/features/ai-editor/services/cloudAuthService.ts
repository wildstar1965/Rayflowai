import { editorRequest } from '../../../services/editorClient';
export type CloudProvider = 'dropbox' | 'google-drive';
type CloudAuthPayload = { accessToken: string; expiresAt?: number; accountId?: string };
let connections: { id: string; configured: boolean; connected: boolean }[] = [];
export async function refreshCloudConnections() {
  connections = (await editorRequest('/editor/cloud')).providers;
  return connections;
}
export const getCloudClientId = (provider: CloudProvider) => connections.find(row => row.id === provider)?.configured ? 'Configured on backend' : '';
export const setCloudClientId = (_provider: CloudProvider, _value: string) => { throw new Error('The backend operator configures OAuth client IDs.'); };
export const getCloudAuth = (provider: CloudProvider): CloudAuthPayload | null => connections.find(row => row.id === provider)?.connected ? { accessToken: 'rayflow-managed:configured' } : null;
export const setCloudAuth = (_provider: CloudProvider, _auth: unknown) => { throw new Error('Connect cloud accounts through Rayflow Connections.'); };
export const clearCloudAuth = async (provider: CloudProvider) => {
  await editorRequest(`/editor/cloud/${provider}`, { method: 'DELETE' });
  await refreshCloudConnections();
};
export const startCloudOAuth = async (provider: CloudProvider) => {
  const { saveBeforeWorkspaceChange } = await import('../../../services/workspaceNavigation');
  if (!await saveBeforeWorkspaceChange()) throw new Error('Save the current project before connecting cloud storage.');
  const { url } = await editorRequest(`/editor/cloud/${provider}/start`, { method: 'POST' });
  window.location.assign(url);
};
export const handleCloudOAuthCallback = async () => { await refreshCloudConnections(); return false; };
export const getValidCloudAuth = async (provider: CloudProvider) => { await refreshCloudConnections(); return getCloudAuth(provider); };
