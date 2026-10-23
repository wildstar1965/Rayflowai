import { useEffect, useState } from 'react';
import { editorRequest } from '../services/editorClient';
import { ensureActiveProject } from '../services/sharedProjects';
import { saveBeforeWorkspaceChange } from '../services/workspaceNavigation';

export default function TeamConnections() {
  const [user, setUser] = useState<any>(null);
  const [teams, setTeams] = useState<any[]>([]);
  const [selected, setSelected] = useState('');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [invite, setInvite] = useState('');
  const [role, setRole] = useState('editor');
  const [message, setMessage] = useState('');
  const [activity, setActivity] = useState<any>({ messages: [], presence: [] });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const refresh = async () => {
    const status = await editorRequest('/editor/account'); setUser(status.user);
    if (status.user) setTeams((await editorRequest('/editor/teams')).teams);
  };
  useEffect(() => { void refresh().catch(err => setError(err.message)); }, []);
  useEffect(() => {
    if (!selected) return;
    let stopped = false;
    const update = async () => {
      try {
        await editorRequest(`/editor/teams/${selected}/activity`, { method: 'POST', body: '{}' });
        const next = await editorRequest(`/editor/teams/${selected}/activity`);
        if (!stopped) setActivity(next);
      } catch (err) { if (!stopped) setError(err instanceof Error ? err.message : 'Team is unavailable.'); }
    };
    void update(); const timer = setInterval(() => void update(), 10000);
    return () => { stopped = true; clearInterval(timer); };
  }, [selected]);
  const action = async (path: string, body: any) => {
    setError(''); return editorRequest('/editor/teams' + path, { method: 'POST', body: JSON.stringify(body) });
  };
  return <section><h2>Teams and shared projects</h2>{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!user ? <p><a href="#/connections">Sign in through Connections</a> to join a team. Guest editing remains available.</p> : <>
      <form onSubmit={event => { event.preventDefault(); void action('', { name }).then(refresh).catch(err => setError(err.message)); }}>
        <label>Team name<input required value={name} onChange={event => setName(event.target.value)} maxLength={120} /></label><button>Create team</button>
      </form>
      <form onSubmit={event => { event.preventDefault(); void action('/join', { code }).then(refresh).catch(err => setError(err.message)); }}>
        <label>Invitation code<input required value={code} onChange={event => setCode(event.target.value)} /></label><button>Join team</button>
      </form>
      <label>Team<select value={selected} onChange={event => { setSelected(event.target.value); setInvite(''); }}><option value="">Choose a team</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name} ({team.role})</option>)}</select></label>
      {selected && <>
        {teams.find(team => team.id === selected)?.role === 'owner' && <div><label>Invitation access<select value={role} onChange={event => setRole(event.target.value)}><option value="editor">Editor</option><option value="viewer">Viewer</option></select></label>
          <button onClick={() => void action(`/${selected}/invite`, { role }).then(result => setInvite(result.code)).catch(err => setError(err.message))}>Create invitation</button>
          {invite && <label>Share this one-use code (expires in 24 hours)<input readOnly value={invite} onFocus={event => event.target.select()} /></label>}
        </div>}
        <button onClick={() => void (async () => {
          if (!await saveBeforeWorkspaceChange()) return;
          const project = await ensureActiveProject();
          await action(`/${selected}/share`, { project_id: project.id });
          setNotice('A shared copy is available in Projects. The original project remains in your workspace.');
        })().catch(err => setError(err.message))}>Share a copy of the current project</button>
        <p>Online: {activity.presence.map((entry: any) => entry.name).join(', ') || 'No active members'}</p>
        <form onSubmit={event => { event.preventDefault(); void action(`/${selected}/activity`, { message }).then(async () => { setMessage(''); setActivity(await editorRequest(`/editor/teams/${selected}/activity`)); }).catch(err => setError(err.message)); }}>
          <label>Team message<input value={message} required maxLength={4000} onChange={event => setMessage(event.target.value)} /></label><button>Send message</button>
        </form><ul>{activity.messages.map((entry: any) => <li key={entry.id}><strong>{entry.name}: </strong>{entry.message}</li>)}</ul>
      </>}
    </>}
  </section>;
}
