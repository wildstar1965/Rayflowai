import { useEffect, useState } from 'react';
import { editorRequest, uploadEditorAsset } from '../services/editorClient';

export default function SharedAssets() {
  const [open, setOpen] = useState(false);
  const [assets, setAssets] = useState<Record<string, any>[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = async () => setAssets((await editorRequest('/editor/assets')).assets.filter((asset: any) => !asset.pending));
  useEffect(() => {
    const show = () => { setOpen(true); setError(''); void refresh().catch(err => setError(err.message)); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    window.addEventListener('rayflow:assets', show); window.addEventListener('keydown', escape);
    return () => { window.removeEventListener('rayflow:assets', show); window.removeEventListener('keydown', escape); };
  }, []);
  if (!open) return null;
  return <div className="rayflow-modal-backdrop"><section className="rayflow-modal" role="dialog" aria-modal="true" aria-labelledby="shared-assets-title">
    <div className="workspace-actions"><h1 id="shared-assets-title">Project assets</h1><button onClick={() => setOpen(false)}>Close</button></div>
    <p>Uploads from Studio and AI Editor are available in this private workspace.</p>
    {error && <p role="alert">{error}</p>}
    <label>Upload files<input type="file" multiple disabled={busy} onChange={event => {
      const files = Array.from(event.target.files || []); setBusy(true); setError('');
      void (async () => { for (const file of files) await uploadEditorAsset(file); await refresh(); })()
        .catch(err => setError(err.message)).finally(() => setBusy(false));
    }} /></label>
    {busy && <p role="status">Uploading media…</p>}
    <ul className="project-list">{assets.map(asset => <li key={asset.id}>
      <span>{asset.name}</span><span>{asset.type}</span><a href={asset.url} download>Download</a>
      <button onClick={() => {
        if (!/^#\/(editor|studio)/.test(window.location.hash)) { setError('Open Studio or AI Editor to use an asset.'); return; }
        window.dispatchEvent(new CustomEvent('rayflow:insert-asset', { detail: asset })); setOpen(false);
      }}>Use in current workspace</button>
    </li>)}</ul>
    {!assets.length && <p>Upload media here or in either editor to start your library.</p>}
  </section></div>;
}
