import { useEffect, useState } from 'react';
import { backendRequest } from '../services/settings';
import { getDownloadUrl } from '../services/api';
import { editorRequest, getWorkspaceSession } from '../services/editorClient';
interface Analytics {
  total_jobs: number; active_jobs: number; completed_jobs: number; failed_jobs: number;
  cancelled_jobs: number; interrupted_jobs: number;
  exports: number; caption_jobs: number; average_render_seconds: number | null; success_rate: number | null;
  daily_activity: { date: string; completed: number; failed: number; exports: number }[];
  recent_jobs: { id: string; kind: string; status: string; created: number; started: number | null; finished: number | null; output: string | null; editor?: boolean; retryable?: boolean; error?: string; can_refresh_provider?: boolean; provider_status?: string }[];
}
export default function DashboardPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [project, setProject] = useState<any>(null);
  useEffect(() => {
    const identity = getWorkspaceSession()?.preferences.activeProject;
    if (identity) void editorRequest(`/editor/projects/${identity}`).then(setProject).catch(err => setError(err.message));
  }, []);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const update = async () => {
      try { const result = await backendRequest<Analytics>('/analytics'); if (!disposed) { setData(result); setUpdatedAt(new Date()); setError(''); } }
      catch (err) { if (!disposed) setError(err instanceof Error ? err.message : 'Could not load activity.'); }
      finally { if (!disposed) timer = setTimeout(update, 5000); }
    };
    void update();
    const onFocus = () => setRefresh(value => value + 1);
    window.addEventListener('focus', onFocus);
    window.addEventListener('storage', onFocus);
    return () => { disposed = true; clearTimeout(timer); window.removeEventListener('focus', onFocus); window.removeEventListener('storage', onFocus); };
  }, [refresh]);
  let saved: { projectName?: string; plan?: { clips?: unknown[]; subtitles?: unknown[] } } | null = null;
  let projectError = '';
  try {
    const value = project?.sequences?.find((sequence: any) => sequence.id === 'reel-primary')?.document || null;
    if (value !== null && (typeof value !== 'object' || Array.isArray(value) || (value.projectName != null && typeof value.projectName !== 'string'))) throw new Error('Invalid saved project');
    if (value?.plan != null && (typeof value.plan !== 'object' ||
      (value.plan.clips != null && !Array.isArray(value.plan.clips)) ||
      (value.plan.subtitles != null && !Array.isArray(value.plan.subtitles)))) throw new Error('Invalid saved timeline');
    saved = value;
  }
  catch { projectError = 'The saved project could not be read on this device.'; }
  const cards = data ? [
    ['Completed exports', data.exports, 'Completed FFmpeg render jobs recorded by this backend.'],
    ['Caption jobs', data.caption_jobs, 'Completed standalone transcription jobs, including jobs with no detected speech.'],
    ['Active jobs', data.active_jobs, 'Queued + processing render, transcription and creative jobs.'],
    ['Processing success', data.success_rate === null ? '—' : `${data.success_rate.toFixed(1)}%`, 'Completed / (completed + failed). Cancelled and interrupted jobs are excluded.'],
    ['Average render time', data.average_render_seconds === null ? '—' : `${data.average_render_seconds.toFixed(1)} s`, 'Average finish − worker start for completed renders; queue time is excluded.'],
    ['Recorded jobs', data.total_jobs, 'All jobs recorded since persistent tracking was enabled.'],
    ['Failed jobs', data.failed_jobs, 'Processing jobs that ended in failure.'],
    ['Cancelled jobs', data.cancelled_jobs, 'Jobs stopped at the user’s request. Excluded from the success rate.'],
    ['Interrupted jobs', data.interrupted_jobs, 'Unfinished jobs detected at backend startup. Run these jobs again.'],
  ] : [];
  return <main className="workspace-page"><h1>Production dashboard</h1><p>Activity from Studio and AI Editor is saved with your workspace. Provider entries include individual API requests and polling operations.</p>
    <div className="workspace-actions"><a href="#/studio">Continue editing</a><button onClick={() => setRefresh(value => value + 1)}>Refresh activity</button></div>
    {error && <p role="alert" className="connection-error">{error} {data ? 'Previously loaded values are shown.' : ''}</p>}
    {!data && !error && <p role="status">Loading activity…</p>}
    {updatedAt && <p>Last refreshed {updatedAt.toLocaleTimeString()}. Updates every five seconds while this page is open.</p>}
    <section className="project-summary"><h2>{project?.name || saved?.projectName || 'No saved project yet'}</h2><p>{projectError || `${saved?.plan?.clips?.length || 0} Studio clips · ${project?.project?.timelineClips?.length || 0} AI Editor clips`}</p></section>
    <div className="metric-grid">{cards.map(([label, value, formula]) => <article key={label} className="metric-card"><h2>{label}</h2><strong>{value}</strong><p>{formula}</p></article>)}</div>
    {data?.daily_activity && <section><h2>Last seven days</h2><p>Completed and failed jobs grouped by finish date (UTC). Exports are a subset of completed jobs.</p><div className="activity-table"><table><thead><tr><th>Date (UTC)</th><th>Completed</th><th>Failed</th><th>Exports</th></tr></thead><tbody>{data.daily_activity.map(day => <tr key={day.date}><td>{day.date}</td><td>{day.completed}</td><td>{day.failed}</td><td>{day.exports}</td></tr>)}</tbody></table></div></section>}
    {data && <section><h2>Recent processing</h2>{!data.recent_jobs.length ? <p>No processing jobs yet. Create a reel, generate captions, or render a video to see measured activity.</p> : <div className="activity-table"><table><thead><tr><th>Job</th><th>Status</th><th>Created</th><th>Result</th></tr></thead><tbody>{data.recent_jobs.map(job => <tr key={job.id}><td>{job.kind}</td><td>{job.status}</td><td>{new Date(job.created * 1000).toLocaleString()}</td><td>{job.kind === 'render' && job.status === 'completed' ? <a href={getDownloadUrl(job.id)}>Download MP4</a> : '—'}</td></tr>)}</tbody></table></div>}</section>}
    {!!data?.recent_jobs.some(job => job.editor) && <section><h2>Editor jobs</h2><ul>
      {data.recent_jobs.filter(job => job.editor).map(job => <li key={job.id}>
        <strong>{job.kind}</strong> — {job.status} {job.error && <span>{job.error}</span>}
        {job.output && job.status === 'completed' && <a href={job.output} download>Download result</a>}
        {job.can_refresh_provider && <button onClick={() => void editorRequest(`/editor/jobs/${job.id}/provider-status`, { method: 'POST' }).then(() => setRefresh(value => value + 1)).catch(err => setError(err.message))}>Check existing provider result{job.provider_status ? ` (${job.provider_status})` : ''}</button>}
        {['queued', 'processing'].includes(job.status) && <button onClick={() => void editorRequest(`/editor/jobs/${job.id}/cancel`, { method: 'POST' }).then(() => setRefresh(value => value + 1)).catch(err => setError(err.message))}>Cancel</button>}
        {job.retryable && ['failed', 'interrupted', 'cancelled'].includes(job.status) && <button onClick={() => void editorRequest(`/editor/jobs/${job.id}/retry`, { method: 'POST' }).then(() => setRefresh(value => value + 1)).catch(err => setError(err.message))}>Retry existing job</button>}
      </li>)}
    </ul></section>}
  </main>;
}
