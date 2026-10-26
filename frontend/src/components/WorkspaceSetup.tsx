import { useState } from 'react';
import ProviderConnections from './ProviderConnections';
import { saveWorkspacePreferences } from '../services/editorClient';

export default function WorkspaceSetup({ onClose }: { onClose: () => void }) {
  const [error, setError] = useState('');
  const finish = async () => {
    try { await saveWorkspacePreferences({ setupComplete: true }); onClose(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not save setup preferences.'); }
  };
  return <div className="rayflow-modal-backdrop"><section className="rayflow-modal rayflow-setup-modal" role="dialog" aria-modal="true" aria-labelledby="setup-title">
    <div className="rayflow-modal-body">
    <h1 id="setup-title">Welcome to Rayflow AI</h1>
    <p>Connect Gemini, OpenAI or Anthropic to direct your video edits in ordinary language. You can edit without a key and change providers later in Connections.</p>
    <ProviderConnections quick />
    {error && <p role="alert">{error}</p>}
    </div>
    <div className="workspace-actions"><button onClick={() => void finish()}>Continue to Rayflow</button><button onClick={() => void finish()}>Skip for now</button></div>
  </section></div>;
}
