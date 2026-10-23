import { useEffect, useRef } from 'react';
import { editorRequest, getWorkspaceSession } from './editorClient';
import { ensureActiveProject, saveReelSequence, type SharedProject } from './sharedProjects';
import { registerWorkspaceSave } from './workspaceNavigation';

/** Full-fidelity reel persistence; revision checks protect edits in another tab. */
export function useSharedReel(snapshot: Record<string, any>, restore: (document: Record<string, any>) => void,
                              report: (message: string) => void, hydrated: boolean, setHydrated: (value: boolean) => void) {
  const current = useRef(snapshot); current.current = snapshot;
  const callbacks = useRef({ restore, report, setHydrated }); callbacks.current = { restore, report, setHydrated };
  const projectId = useRef('');
  const readOnly = useRef(false);
  const revision = useRef(0);
  const savedJson = useRef('');
  const saveQueue = useRef(Promise.resolve());
  const flush = () => {
    const id = projectId.current;
    const document = current.current;
    const serialized = JSON.stringify(document);
    if (!id || readOnly.current || serialized === savedJson.current) return saveQueue.current;
    // Retry the same revision after transient failures; a conflict still cannot overwrite newer work.
    saveQueue.current = saveQueue.current.catch(() => undefined).then(async () => {
      if (serialized === savedJson.current) return;
      const saved = await saveReelSequence(id, document, revision.current);
      revision.current = saved.revision; savedJson.current = serialized;
    }).catch(error => { callbacks.current.report(`Autosave failed: ${error.message}`); throw error; });
    return saveQueue.current;
  };
  const latestFlush = useRef(flush); latestFlush.current = flush;
  useEffect(() => registerWorkspaceSave(async () => {
    try { await latestFlush.current(); return true; } catch { return false; }
  }), []);
  useEffect(() => {
    let disposed = false;
    const load = async (id?: string) => {
      callbacks.current.setHydrated(false);
      try {
        await flush();
        const project = id ? await editorRequest<SharedProject>(`/editor/projects/${id}`) : await ensureActiveProject();
        if (disposed) return;
        projectId.current = project.id;
        readOnly.current = project.read_only === true;
        const sequence = project.sequences?.find(item => item.id === 'reel-primary');
        revision.current = sequence?.revision || 0;
        if (sequence) {
          savedJson.current = JSON.stringify(sequence.document);
          callbacks.current.restore(sequence.document);
        } else {
          // A new shared project starts a fresh reel without copying the previous one.
          callbacks.current.restore({ projectName: project.name, images: [], audio: null, audioAnalysis: null,
            plan: { ...current.current.plan, clips: [], transitions: [] } });
          savedJson.current = '';
        }
      } catch (error) { callbacks.current.report(error instanceof Error ? error.message : 'Could not restore project.'); }
      finally { if (!disposed) callbacks.current.setHydrated(true); }
    };
    void load();
    const open = (event: Event) => { void load((event as CustomEvent<string>).detail); };
    const save = () => { void flush().catch(() => undefined); };
    window.addEventListener('rayflow:open-project', open);
    window.addEventListener('rayflow:save-project', save);
    return () => { disposed = true; save(); window.removeEventListener('rayflow:open-project', open); window.removeEventListener('rayflow:save-project', save); };
  }, []);
  const serialized = JSON.stringify(snapshot);
  useEffect(() => {
    if (!hydrated || !projectId.current) return;
    const key = `rayflow:${getWorkspaceSession()?.workspace_id}:reel:${projectId.current}`;
    try { localStorage.setItem(key, serialized); } catch { /* backend autosave remains authoritative */ }
    const timer = setTimeout(() => { void flush().catch(() => undefined); }, 900);
    return () => clearTimeout(timer);
  }, [serialized, hydrated]);
  return readOnly.current;
}
