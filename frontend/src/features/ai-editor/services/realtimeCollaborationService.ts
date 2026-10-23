import { editorRequest } from '../../../services/editorClient';
import type { ProjectCollaborativeLock, ProjectCollaborationPresence, ProjectCollaborator, ProjectRealtimeEnvelope, ProjectRealtimeEventType } from '../types';
export type ProjectRealtimeStatus = 'SUBSCRIBED' | 'CHANNEL_ERROR' | 'TIMED_OUT' | 'CLOSED';
export type ProjectRealtimeSessionCallbacks = {
  onStatus?: (status: ProjectRealtimeStatus) => void;
  onPresence?: (presence: ProjectCollaborationPresence[]) => void;
  onEvent?: (event: ProjectRealtimeEnvelope) => void;
};
export type ProjectRealtimeSession = {
  channelName: string; sessionId: string; connect: () => Promise<boolean>; disconnect: () => Promise<void>;
  updatePresence: (value: Partial<ProjectCollaborationPresence>) => Promise<boolean>;
  broadcast: <T>(type: ProjectRealtimeEventType, payload: T, options?: { revision?: string; source?: ProjectRealtimeEnvelope['source'] }) => Promise<boolean>;
  claimLock: (lock: Omit<ProjectCollaborativeLock, 'claimedAt'>) => Promise<boolean>;
  releaseLock: (scope: ProjectCollaborativeLock['scope'], key: string) => Promise<boolean>;
};
export const createProjectRealtimeSession = (params: {
  projectId: string; collaborator: ProjectCollaborator; sessionId?: string;
  initialPresence?: Partial<ProjectCollaborationPresence>; callbacks?: ProjectRealtimeSessionCallbacks;
}): ProjectRealtimeSession | null => {
  if (!/^[0-9a-f-]{36}$/i.test(params.projectId)) return null;
  const sessionId = params.sessionId || crypto.randomUUID();
  const path = `/editor/collaboration/${params.projectId}`;
  let presence = params.initialPresence || {};
  let stopped = true;
  let timer: ReturnType<typeof setTimeout>;
  const seen = new Set<string>();
  const send = async (value: any) => { await editorRequest(path, { method: 'POST', body: JSON.stringify({ session: sessionId, presence, ...value }) }); return true; };
  const tick = async () => {
    if (stopped) return;
    try {
      await send({});
      const state = await editorRequest(path);
      params.callbacks?.onPresence?.(state.presence);
      for (const event of state.events) if (!seen.has(event.id)) { seen.add(event.id); params.callbacks?.onEvent?.(event); }
      params.callbacks?.onStatus?.('SUBSCRIBED');
    } catch { params.callbacks?.onStatus?.('CHANNEL_ERROR'); }
    if (!stopped) timer = setTimeout(() => void tick(), 1500);
  };
  const broadcast: ProjectRealtimeSession['broadcast'] = async (type, payload, options) => send({ event: { type, payload, revision: options?.revision, source: options?.source || 'local' } });
  return {
    channelName: `project:${params.projectId}`, sessionId,
    connect: async () => { stopped = false; await tick(); return !stopped; },
    disconnect: async () => { stopped = true; clearTimeout(timer); await send({ leave: true }).catch(() => undefined); params.callbacks?.onStatus?.('CLOSED'); },
    updatePresence: async value => { presence = { ...presence, ...value }; return true; },
    broadcast,
    claimLock: async lock => broadcast('lock_claim', { ...lock, claimedAt: new Date().toISOString() }),
    releaseLock: async (scope, key) => broadcast('lock_release', { scope, key, claimedBy: { ...params.collaborator, sessionId } }),
  };
};
