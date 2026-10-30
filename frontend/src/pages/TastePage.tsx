import { useEffect, useMemo, useState } from 'react';
import {
  analyzeTaste,
  getTasteProfile,
  getTasteStrategy,
  saveTasteProfile,
  type TasteAnalysisResponse,
  type TastePreferenceInput,
  type TasteStrategy,
} from '../services/api';

const CATEGORIES: { value: string; label: string }[] = [
  { value: 'movie', label: 'Movie' },
  { value: 'director', label: 'Director' },
  { value: 'artist', label: 'Artist / Musician' },
  { value: 'tv_show', label: 'TV Show' },
  { value: 'book', label: 'Book' },
  { value: 'video_game', label: 'Video Game' },
  { value: 'brand', label: 'Brand' },
  { value: 'genre', label: 'Music / Film genre' },
  { value: 'mood', label: 'Mood' },
  { value: 'aesthetic', label: 'Aesthetic style' },
];

type Row = { id: string; text: string; category: string };

const newRow = (category = 'movie'): Row => ({
  id: Math.random().toString(36).slice(2), text: '', category,
});

export default function TastePage() {
  const [rows, setRows] = useState<Row[]>([newRow('movie'), newRow('director'), newRow('artist')]);
  const [useQloo, setUseQloo] = useState(true);
  const [qlooConfigured, setQlooConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [analysis, setAnalysis] = useState<TasteAnalysisResponse | null>(null);
  const [strategy, setStrategy] = useState<TasteStrategy | null>(null);
  const [strategyMeta, setStrategyMeta] = useState<{ used_qloo: boolean; used_llm: boolean } | null>(null);
  const [hasProfile, setHasProfile] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const profile = await getTasteProfile();
        setQlooConfigured(profile.qloo_configured);
        if (profile.exists && profile.profile) {
          const declared = (profile.profile.declared as TastePreferenceInput[]) || [];
          if (declared.length) {
            setRows(declared.map((d) => ({ id: Math.random().toString(36).slice(2), text: d.text, category: d.category })));
            setHasProfile(true);
          }
        }
      } catch {
        /* first-time users have no profile yet */
      }
    })();
  }, []);

  const validRows = useMemo(() => rows.filter((r) => r.text.trim().length > 0), [rows]);
  const preferences: TastePreferenceInput[] = validRows.map((r) => ({ text: r.text.trim(), category: r.category }));

  const updateRow = (id: string, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const removeRow = (id: string) => setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));

  const runAnalyze = async () => {
    if (!preferences.length) { setError('Add at least one preference first.'); return; }
    setError(''); setStatus('Resolving your preferences with Qloo…'); setLoading(true); setStrategy(null);
    try {
      const result = await analyzeTaste(preferences, useQloo);
      setAnalysis(result);
      setQlooConfigured(result.qloo_configured);
      setStatus('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed.'); setStatus('');
    } finally { setLoading(false); }
  };

  const runSave = async () => {
    if (!preferences.length) { setError('Add at least one preference first.'); return; }
    setError(''); setSaving(true); setStatus('Saving your taste profile…');
    try {
      const result = await saveTasteProfile(preferences, useQloo, hasProfile);
      setHasProfile(true);
      setQlooConfigured(result.qloo_configured);
      if (result.summary) {
        setAnalysis({
          summary: result.summary as TasteAnalysisResponse['summary'],
          resolved_entities: [], resolved_tags: [], cultural_associations: [], unresolved: [],
          qloo_configured: result.qloo_configured,
        });
      }
      setStatus('Taste profile saved. It now personalizes Auto Reel and the AI Director.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save.'); setStatus('');
    } finally { setSaving(false); }
  };

  const runStrategy = async () => {
    setError(''); setStatus('Interpreting your taste into an editing strategy…'); setLoading(true);
    try {
      const result = await getTasteStrategy(true);
      setStrategy(result.strategy);
      setStrategyMeta({ used_qloo: result.used_qloo, used_llm: result.used_llm });
      setStatus('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not generate a strategy. Save your profile first.'); setStatus('');
    } finally { setLoading(false); }
  };

  const summary = analysis?.summary;

  return (
    <main className="workspace-page" style={{ maxWidth: 980, margin: '0 auto', padding: '1.5rem' }}>
      <header style={{ marginBottom: '1rem' }}>
        <h1 style={{ fontSize: '1.8rem', fontWeight: 700 }}>Discover Your Taste</h1>
        <p style={{ opacity: 0.8 }}>
          Tell RayFlow what you love. We use <strong>Qloo Taste AI</strong> to understand your cultural
          preferences, then personalize your edits. Your photos and videos are never sent to Qloo —
          only the cultural preferences below.
        </p>
        {qlooConfigured === false && (
          <p role="status" style={{ marginTop: 8, padding: 10, borderRadius: 8, background: 'rgba(245,158,11,.12)', border: '1px solid rgba(245,158,11,.4)' }}>
            Qloo is not configured on the backend. You can still build a declared-only profile; add
            <code> QLOO_API_KEY</code> on the backend to enable cultural intelligence.
          </p>
        )}
      </header>

      <section aria-label="Your preferences" style={{ display: 'grid', gap: 10 }}>
        {rows.map((row) => (
          <div key={row.id} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              aria-label="Preference category"
              value={row.category}
              onChange={(e) => updateRow(row.id, { category: e.target.value })}
              style={{ padding: '8px 10px', borderRadius: 8, minWidth: 170 }}
            >
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <input
              aria-label="Preference"
              value={row.text}
              placeholder="e.g. Interstellar, Hans Zimmer, lo-fi, noir…"
              onChange={(e) => updateRow(row.id, { text: e.target.value })}
              style={{ flex: 1, padding: '8px 10px', borderRadius: 8 }}
            />
            <button onClick={() => removeRow(row.id)} aria-label="Remove preference" style={{ padding: '8px 12px' }}>✕</button>
          </div>
        ))}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button onClick={() => setRows((p) => [...p, newRow()])} style={{ padding: '8px 12px' }}>+ Add preference</button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
            <input type="checkbox" checked={useQloo} onChange={(e) => setUseQloo(e.target.checked)} />
            Use Qloo cultural intelligence
          </label>
        </div>
      </section>

      <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
        <button onClick={runAnalyze} disabled={loading || saving} style={primaryBtn}>Analyze my taste</button>
        <button onClick={runSave} disabled={loading || saving} style={secondaryBtn}>
          {hasProfile ? 'Update saved profile' : 'Save profile'}
        </button>
        <button onClick={runStrategy} disabled={loading || saving || !hasProfile} style={secondaryBtn}>
          Preview editing strategy
        </button>
      </div>

      {status && <p role="status" style={{ marginTop: 12, opacity: 0.85 }}>{status}</p>}
      {error && <p role="alert" style={{ marginTop: 12, color: '#f87171' }}>{error}</p>}

      {summary && (
        <section aria-label="Taste analysis" style={{ marginTop: 20, display: 'grid', gap: 16 }}>
          <Panel title="You told us (declared preferences)" tone="declared">
            <TagList items={summary.declared.map((d) => `${d.text}`)} empty="No preferences entered." />
          </Panel>
          <Panel title="Qloo matched these entities" tone="qloo">
            <TagList items={summary.resolved_entities.map((e) => `${e.name} · ${e.type.replace('urn:entity:', '')}`)} empty="No entities resolved (declared-only or no Qloo data)." />
          </Panel>
          <Panel title="Qloo-derived cultural associations (inferred, not stated by you)" tone="qloo">
            <TagList items={summary.cultural_associations.map((a) => a.affinity != null ? `${a.name} (${Math.round(a.affinity * 100)}%)` : a.name)} empty="No cultural associations available." />
          </Panel>
          <Panel title="Taste signals used for editing" tone="qloo">
            <TagList items={summary.tag_signals.map((t) => t.name)} empty="No tag signals available." />
          </Panel>
          {summary.notes?.length > 0 && (
            <p style={{ opacity: 0.7, fontSize: '.9rem' }}>{summary.notes.join(' ')}</p>
          )}
        </section>
      )}

      {strategy && (
        <section aria-label="Editing strategy" style={{ marginTop: 20 }}>
          <Panel title={`AI editing interpretation — ${strategy.style_name}`} tone="ai">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 8 }}>
              <Stat label="Pacing" value={strategy.pacing} />
              <Stat label="Color mood" value={strategy.color_mood} />
              <Stat label="Motion" value={strategy.motion} />
              <Stat label="Transitions" value={strategy.transition_preferences.join(', ')} />
              <Stat label="Music direction" value={strategy.music_direction} />
              <Stat label="Storytelling" value={strategy.storytelling} />
              <Stat label="Beat sync" value={strategy.beat_sync ? 'On' : 'Off'} />
              <Stat label="Aspect" value={strategy.aspect_ratio} />
            </div>
            {strategy.reasoning.length > 0 && (
              <ul style={{ marginTop: 12, paddingLeft: 18, display: 'grid', gap: 6 }}>
                {strategy.reasoning.map((r, i) => (
                  <li key={i}><strong>{r.decision}</strong> — <span style={{ opacity: 0.8 }}>{r.basis}</span></li>
                ))}
              </ul>
            )}
            {strategyMeta && (
              <p style={{ marginTop: 10, fontSize: '.85rem', opacity: 0.7 }}>
                {strategyMeta.used_qloo ? 'Informed by real Qloo cultural intelligence.' : 'Based on declared preferences (no Qloo data).'}{' '}
                {strategyMeta.used_llm ? 'Interpreted by your connected AI provider.' : 'Interpreted by the built-in rule engine (no AI key needed).'}
              </p>
            )}
            <p style={{ marginTop: 12 }}>
              Use this in <a href="#/studio">Studio → Auto Reel → “Create a Reel Based on My Taste”</a>, or ask the
              taste-aware AI Director to apply it. Every change is shown for your approval before it is applied.
            </p>
          </Panel>
        </section>
      )}
    </main>
  );
}

const primaryBtn: React.CSSProperties = { padding: '10px 16px', borderRadius: 8, background: '#6366f1', color: 'white', fontWeight: 600 };
const secondaryBtn: React.CSSProperties = { padding: '10px 16px', borderRadius: 8, border: '1px solid rgba(255,255,255,.2)' };

function Panel({ title, tone, children }: { title: string; tone: 'declared' | 'qloo' | 'ai'; children: React.ReactNode }) {
  const toneColor = tone === 'declared' ? 'rgba(99,102,241,.4)' : tone === 'qloo' ? 'rgba(16,185,129,.4)' : 'rgba(245,158,11,.4)';
  const toneLabel = tone === 'declared' ? 'YOU SAID' : tone === 'qloo' ? 'QLOO INFERRED' : 'AI DECIDED';
  return (
    <div style={{ border: `1px solid ${toneColor}`, borderRadius: 12, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: '.7rem', letterSpacing: '.08em', padding: '2px 8px', borderRadius: 999, border: `1px solid ${toneColor}` }}>{toneLabel}</span>
        <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

function TagList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p style={{ opacity: 0.6 }}>{empty}</p>;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {items.map((item, i) => (
        <span key={i} style={{ padding: '4px 10px', borderRadius: 999, background: 'rgba(255,255,255,.07)', fontSize: '.85rem' }}>{item}</span>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 10, borderRadius: 8, background: 'rgba(255,255,255,.05)' }}>
      <div style={{ fontSize: '.7rem', opacity: 0.6, textTransform: 'uppercase', letterSpacing: '.05em' }}>{label}</div>
      <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{value}</div>
    </div>
  );
}
