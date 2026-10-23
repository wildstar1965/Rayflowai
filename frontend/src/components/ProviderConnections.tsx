import { useEffect, useState } from 'react';
import { deleteEditorProvider, editorRequest, getEditorProviders, refreshEditorProviders, saveEditorProvider, type EditorProvider } from '../services/editorClient';

export default function ProviderConnections({ quick = false }: { quick?: boolean }) {
  const [providers, setProviders] = useState<EditorProvider[]>(getEditorProviders);
  const [drafts, setDrafts] = useState<Record<string, { key?: string; model?: string }>>({});
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    const refresh = () => setProviders([...getEditorProviders()]);
    window.addEventListener('rayflow:providers', refresh);
    void refreshEditorProviders().catch(err => setError(err.message));
    return () => window.removeEventListener('rayflow:providers', refresh);
  }, []);
  const run = async (id: string, action: () => Promise<void>) => {
    setBusy(id); setError(''); setMessage('');
    try { await action(); } catch (err) { setError(err instanceof Error ? err.message : 'Connection failed.'); }
    finally { setBusy(''); }
  };
  const field = (id: string, key: 'key' | 'model', value: string) => setDrafts(previous => ({ ...previous, [id]: { ...previous[id], [key]: value } }));
  const shown = quick ? providers.filter(provider => ['gemini', 'fal', 'replicate', 'elevenlabs'].includes(provider.id)) : providers;
  return <section className="rayflow-connections" aria-label="AI provider connections">
    <p>Your keys are encrypted on the backend and belong to this guest workspace. Editing and media import work without a key.</p>
    {error && <p className="connection-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <div className="connection-grid">{shown.map(provider => <section key={provider.id}>
      <h2>{provider.label}</h2>
      <p>{provider.configured ? (provider.tested ? 'Connection verified' : 'Configured') : provider.local ? 'Not configured on the backend' : 'No key saved'}</p>
      {provider.local ? <p>{provider.base_url || 'The host operator can connect this service. A hosted app cannot reach software on your computer automatically.'}</p> :
        <label>API key<input type="password" autoComplete="new-password" value={drafts[provider.id]?.key || ''}
          placeholder={provider.id === 'higgsfield' ? 'KEY_ID:KEY_SECRET' : provider.configured ? 'Leave blank to keep the saved key' : 'Enter your provider key'}
          onChange={event => field(provider.id, 'key', event.target.value)} /></label>}
      <label>Preferred model<input value={drafts[provider.id]?.model ?? provider.model ?? ''}
        list={`models-${provider.id}`} placeholder="Use the workspace model selection" onChange={event => field(provider.id, 'model', event.target.value)} /></label>
      <datalist id={`models-${provider.id}`}>{(models[provider.id] || []).map(model => <option key={model} value={model} />)}</datalist>
      <div className="workspace-actions">
        <button disabled={!!busy} onClick={() => void run(provider.id, async () => {
          const draft = drafts[provider.id] || {};
          if (!provider.local && !provider.configured && !draft.key?.trim()) throw new Error(`Enter your ${provider.label} key.`);
          await saveEditorProvider(provider.id, draft.key, draft.model);
          setDrafts(previous => ({ ...previous, [provider.id]: { model: draft.model } }));
          setMessage(`${provider.label} configuration saved.`);
        })}>Save</button>
        <button disabled={!!busy || !provider.configured} onClick={() => void run(provider.id, async () => {
          const result = await editorRequest(`/editor/providers/${provider.id}/test`, { method: 'POST' });
          if (!result.ok) throw new Error(result.message);
          setMessage(result.message); await refreshEditorProviders();
        })}>Test connection</button>
        {['gemini', 'openrouter', 'xai', 'ollama', 'lmstudio', 'openai-compatible'].includes(provider.id) && <button disabled={!!busy || !provider.configured} onClick={() => void run(provider.id, async () => {
          const result = await editorRequest(`/editor/providers/${provider.id}/models`); setModels(previous => ({ ...previous, [provider.id]: result.models }));
          setMessage(`Found ${result.models.length} models for ${provider.label}.`);
        })}>Find models</button>}
        {!provider.local && provider.configured && <button disabled={!!busy} onClick={() => void run(provider.id, async () => {
          await deleteEditorProvider(provider.id); setMessage(`${provider.label} key removed.`);
        })}>Remove key</button>}
      </div>
    </section>)}</div>
  </section>;
}
