import { useEffect, useState } from 'react';
import { editorRequest } from '../services/editorClient';
import { saveBeforeWorkspaceChange } from '../services/workspaceNavigation';

export default function AccountConnections() {
  const [status, setStatus] = useState<any>(null);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { void editorRequest('/editor/account').then(setStatus).catch(err => setError(err.message)); }, []);
  const submit = async () => {
    setBusy(true); setError('');
    try {
      if (sent) {
        if (!await saveBeforeWorkspaceChange()) return;
        await editorRequest('/editor/account/verify', { method: 'POST', body: JSON.stringify({ email, code }) });
        window.location.reload();
      } else {
        const result = await editorRequest('/editor/account/code', { method: 'POST', body: JSON.stringify({ email }) });
        setSent(true); setMessage(result.message);
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Sign-in failed.'); }
    finally { setBusy(false); }
  };
  const change = async (path: string, body = {}) => {
    if (!await saveBeforeWorkspaceChange()) return;
    await editorRequest('/editor/account/' + path, { method: 'POST', body: JSON.stringify(body) });
    window.location.reload();
  };
  return <section><h2>Optional account</h2><p>Guest editing is available immediately. Sign in to restore workspaces on another browser and use teams.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {status?.user ? <><p>Signed in as {status.user.email}</p>
      <label>Account workspace<select value={status.workspace_id} onChange={event => void change('workspace', { workspace_id: event.target.value }).catch(err => setError(err.message))}>
        {status.workspaces.map((workspace: any) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}
      </select></label><button onClick={() => void change('logout').catch(err => setError(err.message))}>Sign out</button></>
      : status?.configured ? <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <label>Email<input type="email" autoComplete="email" required value={email} onChange={event => { setEmail(event.target.value); setSent(false); }} /></label>
        {sent && <label>Email code<input autoComplete="one-time-code" inputMode="numeric" required pattern="[0-9]{6,10}" value={code} onChange={event => setCode(event.target.value)} /></label>}
        <button disabled={busy} type="submit">{busy ? 'Please wait…' : sent ? 'Verify code' : 'Send sign-in code'}</button>
      </form> : <p>Accounts will be available after the backend Supabase service is configured.</p>}
  </section>;
}
