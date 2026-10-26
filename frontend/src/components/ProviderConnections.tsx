import { useEffect, useState } from 'react';
import { deleteEditorProvider, editorRequest, getEditorProviders, refreshEditorProviders, saveEditorProvider, type EditorProvider } from '../services/editorClient';
import { saveSettings } from '../services/settings';

const draftTestProviders = ['openai', 'anthropic', 'agentrouter', 'gemini'];

function ModelChoice({ provider, discovered, value, onChange }: {
  provider: EditorProvider; discovered?: string[]; value: string; onChange: (value: string) => void;
}) {
  const [custom, setCustom] = useState(false);
  const options = [...new Set(discovered ?? provider.models ?? [])];
  const allowCustom = !['openai', 'anthropic'].includes(provider.id);
  if (!options.length) return <label>Preferred model<input aria-label={`${provider.label} model`} value={value}
    placeholder="Enter a model ID, or use Find models" onChange={event => onChange(event.target.value)} /></label>;
  return <>
    <label>Preferred model<select aria-label={`${provider.label} model`} value={custom ? '__custom' : value}
      onChange={event => { const next = event.target.value; setCustom(next === '__custom'); if (next !== '__custom') onChange(next); }}>
      {!value && <option value="">Use the workspace model selection</option>}
      {value && !options.includes(value) && <option value={value}>{value} (current)</option>}
      {options.map(model => <option key={model} value={model}>{model}</option>)}
      {allowCustom && <option value="__custom">Enter a custom model ID…</option>}
    </select></label>
    {custom && <label>Custom model ID<input aria-label={`${provider.label} custom model`} value={value}
      onChange={event => onChange(event.target.value)} /></label>}
  </>;
}

export default function ProviderConnections({ quick = false }: { quick?: boolean }) {
  const [providers, setProviders] = useState<EditorProvider[]>(getEditorProviders);
  const [drafts, setDrafts] = useState<Record<string, { key?: string; model?: string }>>({});
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
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
  const shown = quick ? providers.filter(provider => draftTestProviders.includes(provider.id)) : providers;
  return <section className="rayflow-connections" aria-label="AI provider connections">
    <p>Your keys are encrypted on the backend and belong to this guest workspace. Editing and media import work without a key.</p>
    {error && <p className="connection-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    <div className="connection-grid">{shown.map(provider => <section key={provider.id}>
      <h2>{provider.label}</h2>
      {provider.id === 'agentrouter' && <p>Use an Agent Router key and the model ID from your account. Test connection makes a short generation request and may use provider credit.</p>}
      {provider.id === 'gemini' && <p>Use a key from <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Google AI Studio</a>. Choose a text model for Studio Director and AI Editor chat. Save the key, then use Find models to load your account’s current choices.</p>}
      <p>{provider.configured ? (provider.tested ? 'Connection verified' : 'Configured') : provider.local ? 'Not configured on the backend' : 'No key saved'}</p>
      {provider.local ? <p>{provider.base_url || 'The host operator can connect this service. A hosted app cannot reach software on your computer automatically.'}</p> :
        <label>API key<input aria-label={`${provider.label} API key`} type={visibleKeys[provider.id] ? 'text' : 'password'} autoComplete="new-password" spellCheck={false} value={drafts[provider.id]?.key || ''}
          placeholder={provider.id === 'higgsfield' ? 'KEY_ID:KEY_SECRET' : provider.configured ? 'Leave blank to keep the saved key' : 'Enter your provider key'}
          onChange={event => field(provider.id, 'key', event.target.value)} />
          <button type="button" aria-label={`${visibleKeys[provider.id] ? 'Hide' : 'Show'} ${provider.label} API key`} aria-pressed={!!visibleKeys[provider.id]}
            onClick={() => setVisibleKeys(previous => ({ ...previous, [provider.id]: !previous[provider.id] }))}>{visibleKeys[provider.id] ? 'Hide key' : 'Show key'}</button></label>}
      <ModelChoice provider={provider} discovered={models[provider.id]}
        value={drafts[provider.id]?.model ?? (provider.model || provider.models?.[0] || '')}
        onChange={value => field(provider.id, 'model', value)} />
      {(drafts[provider.id]?.key?.trim() || (drafts[provider.id]?.model !== undefined && drafts[provider.id]?.model !== (provider.model || provider.models?.[0] || '')))
        && <p>Unsaved changes. Click Save to use this key and model.</p>}
      <div className="workspace-actions">
        <button disabled={!!busy} onClick={() => void run(provider.id, async () => {
          const draft = drafts[provider.id] || {};
          if (!provider.local && !provider.configured && !draft.key?.trim()) throw new Error(`Enter your ${provider.label} key.`);
          await saveEditorProvider(provider.id, draft.key, draft.model ?? (provider.model || provider.models?.[0]));
          if (quick) await saveSettings({ AI_PROVIDER: provider.id });
          setDrafts(previous => ({ ...previous, [provider.id]: { model: draft.model } }));
          setMessage(`${provider.label} configuration saved.`);
        })}>Save</button>
        <button disabled={!!busy || (!provider.configured && !(draftTestProviders.includes(provider.id) && drafts[provider.id]?.key?.trim()))} onClick={() => void run(provider.id, async () => {
          const draft = drafts[provider.id];
          const result = await editorRequest(`/editor/providers/${provider.id}/test`, { method: 'POST', signal: AbortSignal.timeout(135000),
            ...(draftTestProviders.includes(provider.id) ? { body: JSON.stringify({ key: draft?.key, model: draft?.model ?? (provider.model || provider.models?.[0]) }) } : {}) });
          await refreshEditorProviders();
          if (!result.ok) throw new Error(result.message);
          setMessage(result.message);
        })}>Test connection</button>
        {['gemini', 'openrouter', 'agentrouter', 'xai', 'ollama', 'lmstudio', 'openai-compatible'].includes(provider.id) && <button disabled={!!busy || !provider.configured} onClick={() => void run(provider.id, async () => {
          const result = await editorRequest(`/editor/providers/${provider.id}/models`); setModels(previous => ({ ...previous, [provider.id]: result.models }));
          setMessage(result.models.length ? `Found ${result.models.length} models for ${provider.label}. Choose a model and click Save.` : `No compatible models were returned for ${provider.label}. Check your account’s model access.`);
        })}>Find models</button>}
        {!provider.local && provider.configured && <button disabled={!!busy} onClick={() => void run(provider.id, async () => {
          await deleteEditorProvider(provider.id); setMessage(`${provider.label} key removed.`);
        })}>Remove key</button>}
      </div>
      {busy === provider.id && <p role="status">Connecting…</p>}
    </section>)}</div>
  </section>;
}
