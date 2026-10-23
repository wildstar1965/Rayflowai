import { editorRequest } from '../../../services/editorClient';
export type StudioAuthUser = { id: string; email: string; name: string };
export const resolveStudioUser = async (): Promise<StudioAuthUser | null> => (await editorRequest('/editor/account')).user;
export const loginWithEmail = async (_email: string) => { window.location.hash = '#/connections'; };
export const loginWithProvider = async (_provider: 'google' | 'discord') => { window.location.hash = '#/connections'; };
export const logoutStudio = async () => {
  await editorRequest('/editor/account/logout', { method: 'POST' });
  window.location.reload();
};
export const onStudioAuthChange = (callback: (user: StudioAuthUser | null) => void) => {
  let disposed = false;
  void resolveStudioUser().then(user => { if (!disposed) callback(user); }).catch(() => { if (!disposed) callback(null); });
  return () => { disposed = true; };
};
