import * as Y from 'yjs';
import { editorRequest } from '../../../services/editorClient';
import { encodeBinary } from './transport';
import { registerWorkspaceSave } from '../../../services/workspaceNavigation';

/** Durable HTTP relay for Yjs; no public room credentials or browser auth tokens. */
export class HostedCollaborationProvider {
  connected = false;
  synced = false;
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;
  private session = crypto.randomUUID();
  private seen = new Set<string>();
  private updates: Uint8Array[] = [];
  private selection: Record<string, unknown> = {};
  private inFlight: Promise<void> = Promise.resolve();
  private unregister: () => void;
  private readOnly = false;
  awareness = { getLocalState: () => ({ selection: this.selection }) };
  constructor(private options: { projectId: string; document: Y.Doc; onStatus: (event: { status: string }) => void;
                                onAwarenessChange: (event: { states: any[] }) => void }) {
    options.document.on('update', this.onUpdate);
    this.unregister = registerWorkspaceSave(async () => {
      try { await this.flush(); return true; } catch { return false; }
    });
  }
  private onUpdate = (update: Uint8Array, origin: unknown) => { if (origin !== this) this.updates.push(update); };
  setAwarenessField(_field: string, value: Record<string, unknown>) { this.selection = value; }
  async connect() {
    this.stopped = false;
    const initial = await editorRequest(`/editor/collaboration/${encodeURIComponent(this.options.projectId)}`);
    if (this.stopped) return;
    this.readOnly = initial.readOnly === true;
    this.apply(initial);
    this.synced = true; this.connected = true;
    this.options.onStatus({ status: 'connected' });
    this.timer = setTimeout(() => void this.tick(), 1000);
  }
  private apply(state: any) {
    for (const update of state.updates) if (!this.seen.has(update.id)) {
      Y.applyUpdate(this.options.document, Uint8Array.from(atob(update.data), character => character.charCodeAt(0)), this);
      this.seen.add(update.id);
    }
    this.options.onAwarenessChange({ states: state.presence.filter((entry: any) => entry.selection) });
  }
  private async tick() {
    if (this.stopped) return;
    try {
      await this.flush();
      this.apply(await editorRequest(`/editor/collaboration/${encodeURIComponent(this.options.projectId)}`));
      this.connected = true; this.options.onStatus({ status: 'connected' });
    } catch {
      this.connected = false; this.options.onStatus({ status: 'disconnected' });
    }
    if (!this.stopped) this.timer = setTimeout(() => void this.tick(), 1000);
  }
  flush() {
    this.inFlight = this.inFlight.catch(() => undefined).then(async () => {
      const pending = this.updates.splice(0);
      try {
        const update = !this.readOnly && pending.length ? await encodeBinary(Y.mergeUpdates(pending).slice().buffer as ArrayBuffer) : undefined;
        await editorRequest(`/editor/collaboration/${encodeURIComponent(this.options.projectId)}`, {
          method: 'POST', body: JSON.stringify({ session: this.session, update, presence: { selection: this.selection } }),
        });
      } catch (error) { this.updates.unshift(...pending); throw error; }
    });
    return this.inFlight;
  }
  disconnect() {
    this.stopped = true; this.connected = false; clearTimeout(this.timer);
    void this.flush().then(() => editorRequest(`/editor/collaboration/${encodeURIComponent(this.options.projectId)}`, {
      method: 'POST', body: JSON.stringify({ session: this.session, leave: true }),
    })).catch(() => undefined);
  }
  destroy() { this.unregister(); this.options.document.off('update', this.onUpdate); }
}
