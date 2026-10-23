import type { useSpeechModels } from './useSpeechModels';

export function SpeechModelSelect({ state, value, onChange, label }: {
  state: ReturnType<typeof useSpeechModels>; value: string; onChange: (value: string) => void; label: string;
}) {
  const selected = state.catalog?.models.find(model => model.id === value);
  return <div className="space-y-1 text-xs">
    <label>Local speech model<select aria-label={label} className="w-full rounded border border-studio-border bg-studio-panel p-1" value={value} onChange={e => onChange(e.target.value)}>
      {!value && <option value="">{state.catalog?.checking || !state.catalog ? 'Checking local models…' : 'No verified model'}</option>}
      {state.catalog?.models.map(model => <option key={model.id} value={model.id} disabled={model.status !== 'ready'}>
        {model.label} — {model.status === 'ready' ? `${model.device}/${model.compute_type}` : model.status === 'missing' ? 'not cached' : model.status}
      </option>)}
    </select></label>
    <p role="status">{state.error || (state.catalog?.checking ? 'Checking cached models with local inference…' : selected?.notice || state.catalog?.notice || selected?.message)}</p>
    <p className="text-studio-muted">{state.catalog?.performance}</p>
    {!value && state.catalog && !state.catalog.checking && <p>Cache Medium or Small on the backend, then check again.</p>}
    {state.catalog?.models.filter(model => model.status === 'failed').map(model => <p key={model.id} role="alert">{model.label}: {model.message}</p>)}
    <button type="button" className="underline" disabled={state.catalog?.checking} onClick={state.refresh}>Check local models</button>
  </div>;
}
