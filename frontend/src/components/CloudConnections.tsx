import { useEffect, useState } from 'react';
import { editorRequest } from '../services/editorClient';
import { saveBeforeWorkspaceChange } from '../services/workspaceNavigation';

export default function CloudConnections() {
  const [providers, setProviders] = useState<{ id: string; configured: boolean; connected: boolean }[]>([]);
  const [error, setError] = useState('');
  const refresh = async () => setProviders((await editorRequest('/editor/cloud')).providers);
  useEffect(() => { void refresh().catch(err => setError(err.message)); }, []);
  const connect = async (id: string) => {
    if (!await saveBeforeWorkspaceChange()) return;
    const { url } = await editorRequest(`/editor/cloud/${id}/start`, { method: 'POST' });
    window.location.assign(url);
  };
  return <section><h2>Cloud storage</h2><p>Optional Dropbox and Google Drive sync uses encrypted authorization stored on the backend.</p>
    {error && <p role="alert">{error}</p>}
    {providers.map(provider => <article key={provider.id} className="connection-card">
      <h3>{provider.id === 'dropbox' ? 'Dropbox' : 'Google Drive'}</h3>
      <p>{provider.connected ? 'Connected' : provider.configured ? 'Ready to connect' : 'The backend operator must configure an OAuth client.'}</p>
      <button disabled={!provider.configured} onClick={() => void connect(provider.id).catch(err => setError(err.message))}>{provider.connected ? 'Reconnect' : 'Connect'}</button>
      {provider.connected && <button onClick={() => void editorRequest(`/editor/cloud/${provider.id}`, { method: 'DELETE' }).then(refresh).catch(err => setError(err.message))}>Disconnect</button>}
    </article>)}
  </section>;
}
