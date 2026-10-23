import { useEffect, useState } from 'react';
import ProviderConnections from '../components/ProviderConnections';
import WorkspaceSetup from '../components/WorkspaceSetup';
import CloudConnections from '../components/CloudConnections';
import AccountConnections from '../components/AccountConnections';
import TeamConnections from '../components/TeamConnections';
import { getSettings, saveSettings } from '../services/settings';

export default function SettingsPage() {
  const [provider, setProvider] = useState('auto');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [setup, setSetup] = useState(false);
  useEffect(() => { void getSettings().then(settings => setProvider(settings.ai_provider)).catch(err => setError(err.message)); }, []);
  return <main className="workspace-page">
    <div className="workspace-actions"><h1>Connections</h1><button onClick={() => setSetup(true)}>Open setup guide</button></div>
    <p>Editing and importing work without provider keys. Available exports and speech models use the backend configuration.</p>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <form onSubmit={event => {
      event.preventDefault(); setError(''); setMessage('');
      void saveSettings({ AI_PROVIDER: provider }).then(() => setMessage('Director preference saved.')).catch(err => setError(err.message));
    }}><label>Studio AI director<select value={provider} onChange={event => setProvider(event.target.value)}>
      <option value="auto">Automatic</option><option value="ollama">Ollama</option><option value="openrouter">OpenRouter</option><option value="local">Local commands</option>
    </select></label><button type="submit">Save preference</button></form>
    <ProviderConnections />
    <CloudConnections />
    <AccountConnections />
    <TeamConnections />
    {setup && <WorkspaceSetup onClose={() => setSetup(false)} />}
  </main>;
}
