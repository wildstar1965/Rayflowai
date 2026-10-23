import { useEffect, useState } from 'react';
import { editorRequest, saveWorkspacePreferences, type EditorProject } from '../services/editorClient';
import { saveBeforeWorkspaceChange } from '../services/workspaceNavigation';
import type { SharedProject } from '../services/sharedProjects';

export default function ProjectManager() {
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<EditorProject[]>([]);
  const [name, setName] = useState('My Rayflow project');
  const [error, setError] = useState('');
  const [files, setFiles] = useState<SharedProject | null>(null);
  const [resolve, setResolve] = useState<((value: string | null) => void) | null>(null);
  const refresh = async () => { setProjects((await editorRequest('/editor/projects')).projects); };
  useEffect(() => {
    const choose = (event: Event) => {
      setOpen(true); setFiles(null); setError('');
      const callback = (event as CustomEvent).detail?.resolve;
      setResolve(() => callback || null);
      void refresh().catch(err => setError(err.message));
    };
    const browse = (event: Event) => {
      setOpen(true); setError('');
      void editorRequest<SharedProject>(`/editor/projects/${(event as CustomEvent).detail}`).then(setFiles).catch(err => setError(err.message));
    };
    window.addEventListener('rayflow:choose-project', choose);
    window.addEventListener('rayflow:project-files', browse);
    return () => { window.removeEventListener('rayflow:choose-project', choose); window.removeEventListener('rayflow:project-files', browse); };
  }, []);
  const close = () => { resolve?.(null); setResolve(null); setOpen(false); };
  const select = async (project: EditorProject) => {
    if (!resolve && !await saveBeforeWorkspaceChange()) return;
    await saveWorkspacePreferences({ activeProject: project.id });
    if (resolve) resolve(project.id);
    else window.dispatchEvent(new CustomEvent('rayflow:open-project', { detail: project.id }));
    setResolve(null); setOpen(false);
  };
  const sequenceAction = async (sequence: string, kind?: 'rayflow' | 'editor') => {
    if (!files || !await saveBeforeWorkspaceChange()) return;
    const project = await editorRequest<SharedProject>(`/editor/projects/${files.id}`);
    const result = await editorRequest(`/editor/projects/${project.id}/sequences/${sequence}/${kind ? 'transfer' : 'activate'}`, {
      method: 'POST', body: JSON.stringify({ kind, revision: project.revision }),
    });
    if (kind) setFiles(await editorRequest<SharedProject>(`/editor/projects/${project.id}`));
    else {
      await saveWorkspacePreferences({ activeProject: project.id });
      window.dispatchEvent(new CustomEvent('rayflow:open-project', { detail: project.id }));
      window.location.hash = `#/${result.workspace}`;
      close();
    }
  };
  if (!open) return null;
  return <div className="rayflow-modal-backdrop"><section className="rayflow-modal" role="dialog" aria-modal="true" aria-labelledby="projects-title">
    <div className="workspace-actions"><h1 id="projects-title">{files ? `${files.name} files` : 'Your projects'}</h1><button onClick={close} aria-label="Close projects">Close</button></div>
    {error && <p role="alert">{error}</p>}
    {files ? <><a href={`/api/editor/projects/${files.id}/archive`} download>Download project archive</a>
      <h2>Sequences</h2><p>Transfers create a copy. Opening a copy preserves the previous timeline as another sequence.</p>
      <ul>{files.sequences?.map(sequence => <li key={sequence.id}>
        <span>{sequence.name} ({sequence.kind === 'editor' ? 'AI Editor' : 'Studio'})</span>
        <button disabled={files.read_only} onClick={() => void sequenceAction(sequence.id).catch(err => setError(err.message))}>Open sequence</button>
        <button disabled={files.read_only} onClick={() => void sequenceAction(sequence.id, sequence.kind === 'editor' ? 'rayflow' : 'editor').catch(err => setError(err.message))}>Transfer to {sequence.kind === 'editor' ? 'Studio' : 'AI Editor'}</button>
      </li>)}</ul>
      <h2>Files</h2><ul>{files.files?.map(file => <li key={file}><a href={`/api/editor/projects/${files.id}/files/${file}`} download>{file}</a></li>)}</ul></> : <>
      <form onSubmit={event => { event.preventDefault(); void editorRequest<EditorProject>('/editor/projects', { method: 'POST', body: JSON.stringify({ name, project: {}, kind: 'editor' }) }).then(select).catch(err => setError(err.message)); }}>
        <label>Project name<input required maxLength={200} value={name} onChange={event => setName(event.target.value)} /></label><button type="submit">Create project</button>
      </form>
      <label className="project-import">Import a project archive or JSON<input type="file" accept=".zip,.json" onChange={event => {
        const file = event.target.files?.[0]; if (!file) return;
        const body = new FormData(); body.append('file', file);
        void editorRequest<EditorProject>('/editor/project-import', { method: 'POST', body }).then(select).catch(err => setError(err.message));
      }} /></label>
      <ul className="project-list">{projects.map(project => <li key={project.id}><button onClick={() => void select(project).catch(err => setError(err.message))}>{project.name}</button><button onClick={() => void editorRequest<SharedProject>(`/editor/projects/${project.id}`).then(setFiles).catch(err => setError(err.message))}>Sequences and files</button><a href={`/api/editor/projects/${project.id}/archive`} download>Download</a></li>)}</ul>
      {!projects.length && <p>Create a project or import an existing project to keep your work.</p>}
    </>}
  </section></div>;
}
