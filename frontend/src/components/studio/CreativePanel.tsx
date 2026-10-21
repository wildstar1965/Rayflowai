import { NumericInput } from '../ui/NumericInput';
import { useRef, useState, useLayoutEffect, useEffect } from 'react';
import type { EditingPlan, VisualInsert, SoundCue, CinematicText } from '../../types';
import { creativeRequest, getMediaUrl, waitCreativeJob } from '../../services/api';

interface Result { id: number; media_type: 'image' | 'video'; preview_url: string; tags: string; source_page: string; contributor: string }
interface Props { plan: EditingPlan; currentTime: number; onChange: (plan: EditingPlan) => void; onSeek: (time: number) => void }
const field = 'w-full min-w-0 rounded border border-zinc-300 bg-white px-2 py-1.5 text-xs';
const button = 'rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 disabled:opacity-40';

export function CreativePanel({ plan, currentTime, onChange, onSeek }: Props) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<'image' | 'video'>('video');
  const [results, setResults] = useState<Result[]>([]);
  const [replaceId, setReplaceId] = useState<string | null>(null);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [maskJob, setMaskJob] = useState<string | null>(null);
  const latest = useRef(plan);
  useLayoutEffect(()=>{latest.current=plan;},[plan]);
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(()=>()=>{audio.current?.pause();},[]);
  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setMessage('');
    try { await work(); } catch (error) { setMessage(error instanceof Error ? error.message : 'The operation failed.'); }
    finally { setBusy(''); setMaskJob(null); }
  }
  async function edit(endpoint: string, body: unknown) {
    const before = latest.current;
    const updated = await creativeRequest<EditingPlan>(endpoint, body);
    if (before !== latest.current) throw new Error('The project changed during processing. Your edits were preserved; please run again.');
    onChange(updated);
    setMessage(updated.warnings?.join(' ') || '');
  }
  function updateInsert(id: string, patch: Partial<VisualInsert>) {
    onChange({ ...plan, visual_inserts: (plan.visual_inserts || []).map(i => i.id === id ? { ...i, ...patch, origin: 'manual' } : i) });
  }
  function updateSound(id: string, patch: Partial<SoundCue>) {
    onChange({ ...plan, sound_cues: (plan.sound_cues || []).map(i => i.id === id ? { ...i, ...patch, origin: 'manual' } : i) });
  }
  function updateTitle(id: string, patch: Partial<CinematicText>) {
    onChange({ ...plan, cinematic_texts: (plan.cinematic_texts || []).map(t => t.id === id ? { ...t, ...patch, origin: 'manual' } : t) });
  }
  function prepareBackground(ins: VisualInsert) {
    return run('Preparing background composition', async () => {
      const clip=plan.clips.find(c=>c.media_type==='video'&&c.start_time<=ins.start_time&&ins.start_time+ins.duration<=c.start_time+c.duration);
      if(!clip)throw new Error('Keep the background insert within one speaker video clip.');
      const prepared={...plan,visual_inserts:plan.visual_inserts?.map(i=>i.id===ins.id?{...i,mode:'background' as const,origin:'manual' as const}:i)};
      const before=latest.current;
      const job=await creativeRequest<{job_id:string}>('/cinematic/prepare',{plan:prepared,clip_id:clip.id});
      setMaskJob(job.job_id);
      await waitCreativeJob(job.job_id,setBusy);
      if(before!==latest.current)throw new Error('The project changed; prepare the background again.');
      onChange(prepared);
    });
  }
  return <div className="space-y-5 text-xs text-zinc-700">
    <section className="space-y-2" aria-label="B-roll controls">
      <h3 className="font-semibold text-zinc-950">Contextual B-roll</h3>
      <label className="flex items-center gap-2"><input type="checkbox" checked={plan.auto_broll !== false}
        onChange={e => onChange({ ...plan, auto_broll: e.target.checked })} />Automatic B-roll</label>
      <button className={button} disabled={!!busy || !plan.subtitles?.length || plan.auto_broll === false}
        onClick={() => run('Finding relevant media', () => edit('/broll/regenerate', plan))}>Regenerate B-roll</button>
      <p className="text-zinc-500">Manual replacements, timing edits, and removed suggestions are preserved.</p>
      <form className="flex gap-1" onSubmit={event => { event.preventDefault(); run('Searching Pixabay', async () => {
        const response = await creativeRequest<{results: Result[]}>(`/broll/search?q=${encodeURIComponent(query)}&kind=${kind}&aspect_ratio=${plan.aspect_ratio}`);
        setResults(response.results); if (!response.results.length) setMessage('No matching media. Try a more concrete phrase.');
      }); }}>
        <input aria-label="Search Pixabay" className={field} value={query} onChange={e => setQuery(e.target.value)} placeholder="Mountain, biryani, circuit board…" required maxLength={100} />
        <select aria-label="B-roll media type" value={kind} onChange={e => setKind(e.target.value as 'image' | 'video')} className="border rounded text-xs">
          <option value="video">Video</option><option value="image">Image</option>
        </select><button className={button} disabled={!!busy}>Search</button>
      </form>
      {replaceId && <p>Replacing selected insert. <button className="underline" onClick={() => setReplaceId(null)}>Cancel replacement</button></p>}
      {!!results.length && <p>Results from <a href="https://pixabay.com" target="_blank" rel="noreferrer" className="underline">Pixabay</a></p>}
      <div className="grid grid-cols-2 gap-2">
        {results.slice(0, 12).map(asset => <div key={`${asset.media_type}-${asset.id}`} className="space-y-1">
          {asset.preview_url && <img src={asset.preview_url} alt={asset.tags} className="w-full aspect-video object-cover rounded" />}
          <a href={asset.source_page} target="_blank" rel="noreferrer" className="block truncate underline">{asset.contributor || 'Pixabay'} · Source</a>
          <button className={button} disabled={!!busy || !plan.clips.length} onClick={() => run('Downloading selected media', async () => {
            await edit('/broll/select', { plan, asset_id: asset.id, kind: asset.media_type, replace_id: replaceId,
              start_time: Math.min(currentTime, Math.max(0, plan.duration_seconds - .5)), duration: 2.5 }); setReplaceId(null);
          })}>{replaceId ? 'Replace with this' : 'Insert at playhead'}</button>
        </div>)}
      </div>
      {(plan.visual_inserts || []).map((ins, index) => <div key={ins.id} data-insert-id={ins.id} className="border-t border-zinc-200 pt-2 space-y-2">
        <button onClick={() => onSeek(ins.start_time)} className="font-medium text-left">{index+1}. {ins.label || 'B-roll'}</button>
        {ins.media_type === 'video' ? <video src={getMediaUrl(ins.asset_url)} controls muted preload="metadata" className="w-full max-h-32 rounded" /> :
          <img src={getMediaUrl(ins.asset_url)} alt={ins.label || 'B-roll'} className="w-full max-h-32 object-contain rounded" />}
        {ins.source_page && <a href={ins.source_page} target="_blank" rel="noreferrer" className="underline block">Pixabay · {ins.contributor || 'Source'}</a>}
        <div className="grid grid-cols-2 gap-2">
          <label>Start (s)<NumericInput aria-label={`Insert ${index+1} start`} min={0} max={Math.max(0,plan.duration_seconds-ins.duration)} step={.1}
            className={field} value={ins.start_time} onCommit={nextValue => updateInsert(ins.id, { start_time: Math.max(0,Math.min(plan.duration_seconds-ins.duration,nextValue)) })} /></label>
          <label>Duration (s)<NumericInput aria-label={`Insert ${index+1} duration`} min={.1} max={plan.duration_seconds-ins.start_time} step={.1}
            className={field} value={ins.duration} onCommit={nextValue => updateInsert(ins.id, { duration: Math.max(.1,Math.min(plan.duration_seconds-ins.start_time,nextValue)) })} /></label>
        </div>
        <select aria-label={`Insert ${index+1} layout`} className={field} value={ins.mode} disabled={!!busy} onChange={e => {
          if(e.target.value!=='background'){updateInsert(ins.id,{mode:e.target.value as VisualInsert['mode']});return;}
          void prepareBackground(ins);
        }}>
          <option value="split">Split screen · keep speaker visible</option><option value="pip">Picture in picture</option><option value="floating">Floating image</option><option value="cutaway">Full-screen cutaway</option><option value="background">Background · retain speaker</option>
        </select>
        {ins.mode === 'background' && <div className="space-y-1">
          <button className={button} disabled={!!busy} onClick={() => void prepareBackground(ins)}>Refresh speaker mask</button>
          <p className="text-zinc-500">Refresh after changing timing, trimming the speaker clip, or changing the framing.</p>
        </div>}
        <select aria-label={`Insert ${index+1} position`} className={field} value={ins.position} onChange={e => updateInsert(ins.id, {position: e.target.value as VisualInsert['position']})}>
          <option value="top_right">Top right</option><option value="top_left">Top left</option><option value="bottom_right">Lower right</option><option value="center">Center</option>
        </select>
        <div className="flex gap-2"><button className={button} onClick={() => { setReplaceId(ins.id); setQuery(ins.query || ins.label || ''); }}>Find replacement</button>
          <button className={button} onClick={() => onChange({ ...plan, visual_inserts: plan.visual_inserts?.filter(i => i.id !== ins.id),
            suppressed_auto_inserts: [...new Set([...(plan.suppressed_auto_inserts || []), ins.id])] })}>Remove</button></div>
      </div>)}
    </section>
    <section className="space-y-2 border-t border-zinc-300 pt-4" aria-label="List sound controls">
      <h3 className="font-semibold text-zinc-950">Spoken-list clicks</h3>
      <label className="flex gap-2 items-center"><input type="checkbox" checked={plan.list_sounds !== false}
        onChange={e => onChange({ ...plan, list_sounds: e.target.checked })} />Enable list sounds</label>
      <button className={button} disabled={!!busy || !plan.subtitles?.length} onClick={() => run('Detecting lists', () => edit('/sounds/detect', plan))}>Detect list items</button>
      {!plan.sound_cues?.length && <p className="text-zinc-500">Clicks appear only for detected spoken lists with word timestamps.</p>}
      {(plan.sound_cues || []).map((cue, index) => <div key={cue.id} data-cue-id={cue.id} className="border-t pt-2 space-y-1">
        <div className="flex gap-2"><button className="truncate text-left" onClick={() => onSeek(cue.start_time)}>{index+1}. {cue.label}</button>
          <label className="ml-auto flex gap-1"><input aria-label={`Mute click ${index+1}`} type="checkbox" checked={cue.muted} onChange={e => updateSound(cue.id,{ muted:e.target.checked })} />Mute</label></div>
        <div className="flex gap-2 items-center"><select aria-label={`Click ${index+1} sound`} className={field} value={cue.sound} onChange={e => updateSound(cue.id, { sound:e.target.value as SoundCue['sound'] })}>
          <option value="soft">Soft</option><option value="wood">Wood</option><option value="tick">Tick</option></select>
          <button className={button} onClick={() => { audio.current?.pause(); const player=new Audio(getMediaUrl(`/api/sounds/${cue.sound}.wav`)); audio.current=player; player.volume=cue.volume; player.play().catch(() => setMessage('Sound preview could not play.')); }}>Listen</button>
        </div>
        <label className="flex items-center gap-2">Volume<input aria-label={`Click ${index+1} volume`} type="range" min={0} max={1} step={.05} value={cue.volume}
          onChange={e => updateSound(cue.id,{volume:Number(e.target.value)})} /></label>
        <label>Time (s)<NumericInput aria-label={`Click ${index+1} time`} className={field} min={0} max={plan.duration_seconds} step={.01} value={cue.start_time}
          onCommit={nextValue => updateSound(cue.id,{start_time:Math.min(plan.duration_seconds,Math.max(0,nextValue))})} /></label>
      </div>)}
    </section>
    <section className="space-y-2 border-t border-zinc-300 pt-4" aria-label="Cinematic typography controls">
      <h3 className="font-semibold text-zinc-950">Cinematic typography</h3>
      <button className={button} disabled={!plan.clips.length} onClick={() => {
        const clip=plan.clips.find(c => currentTime>=c.start_time && currentTime<c.start_time+c.duration) || plan.clips[0];
        const start=Math.min(currentTime,clip.start_time+clip.duration-.1);
        onChange({...plan,cinematic_texts:[...(plan.cinematic_texts||[]),{id:crypto.randomUUID(),text:'YOUR STORY',start_time:start,
          duration:Math.min(2.5,clip.start_time+clip.duration-start),source_clip_id:clip.id,behind_subject:false,color:'#F2E9D8',origin:'manual'}]});
      }}>Add display text</button>
      {(plan.cinematic_texts || []).map(title => <div key={title.id} className="space-y-2 border-t pt-2">
        <textarea aria-label="Cinematic text" className={field} rows={3} value={title.text} maxLength={120} onChange={e => updateTitle(title.id,{text:e.target.value})} />
        <p className="text-zinc-500">Use Enter to choose your line breaks.</p>
        <div className="grid grid-cols-2 gap-2">
          <label>Font<select aria-label="Cinematic font" className={field} value={title.font_family??'Anton'} onChange={e=>updateTitle(title.id,{font_family:e.target.value as CinematicText['font_family']})}><option value="Anton">Anton condensed</option><option value="Arial">Arial</option><option value="DejaVu Sans">DejaVu Sans</option></select></label>
          <label>Weight<select aria-label="Cinematic weight" className={field} value={title.font_weight??700} onChange={e=>updateTitle(title.id,{font_weight:Number(e.target.value)})}><option value={400}>Regular</option><option value={700}>Bold</option></select></label>
          <label>Size (% width)<NumericInput aria-label="Cinematic size" className={field} min={3} max={30} value={Math.round((title.font_size_ratio??.15)*100)} onCommit={nextValue =>updateTitle(title.id,{font_size_ratio:Math.max(3,Math.min(30,nextValue))/100})}/></label>
          <label>Tracking<NumericInput aria-label="Cinematic tracking" className={field} min={-2} max={15} step={.5} value={title.tracking??0} onCommit={nextValue =>updateTitle(title.id,{tracking:Math.max(-2,Math.min(15,nextValue))})}/></label>
          <label>Horizontal (%)<NumericInput aria-label="Cinematic horizontal position" className={field} min={5} max={95} value={Math.round((title.x??.5)*100)} onCommit={nextValue =>updateTitle(title.id,{x:Math.max(5,Math.min(95,nextValue))/100})}/></label>
          <label>Vertical (%)<NumericInput aria-label="Cinematic vertical position" className={field} min={5} max={85} value={Math.round((title.y??.09)*100)} onCommit={nextValue =>updateTitle(title.id,{y:Math.max(5,Math.min(85,nextValue))/100})}/></label>
          <label>Alignment<select aria-label="Cinematic alignment" className={field} value={title.alignment??'center'} onChange={e=>updateTitle(title.id,{alignment:e.target.value as CinematicText['alignment']})}><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>
          <label>Fade seconds<NumericInput aria-label="Cinematic fade" className={field} min={0} max={1} step={.05} value={title.animation_seconds??.16} onCommit={nextValue =>updateTitle(title.id,{animation_seconds:Math.max(0,Math.min(1,nextValue))})}/></label>
          <label>Entrance scale (%)<NumericInput aria-label="Cinematic entrance scale" className={field} min={80} max={100} value={Math.round((title.scale_from??.97)*100)} onCommit={nextValue =>updateTitle(title.id,{scale_from:Math.max(80,Math.min(100,nextValue))/100})}/></label>
          <label>Emphasis color<input aria-label="Cinematic emphasis color" type="color" className={field} value={title.highlight_color??'#E7C48C'} onChange={e=>updateTitle(title.id,{highlight_color:e.target.value})}/></label>
        </div>
        <label className="flex gap-2"><input type="checkbox" checked={title.uppercase??true} onChange={e=>updateTitle(title.id,{uppercase:e.target.checked})}/>Uppercase</label>
        <label>Emphasized words<input aria-label="Cinematic emphasized words" className={field} key={title.id+'-emphasis'} defaultValue={title.emphasis_words?.join(' ')??''} onBlur={e=>updateTitle(title.id,{emphasis_words:e.target.value.split(/\s+/).filter(Boolean).slice(0,20)})}/></label>
        <label className="flex gap-2 items-center">Text color<input aria-label="Cinematic text color" type="color" value={title.color} onChange={e => updateTitle(title.id,{color:e.target.value})} /></label>
        <div className="grid grid-cols-2 gap-2"><label>Start (s)<NumericInput aria-label="Cinematic start" className={field} min={0} max={plan.duration_seconds-title.duration} step={.1} value={title.start_time} onCommit={nextValue => updateTitle(title.id,{start_time:Math.max(0,Math.min(plan.duration_seconds-title.duration,nextValue)),behind_subject:false})} /></label>
          <label>Duration (s)<NumericInput aria-label="Cinematic duration" className={field} min={.1} max={plan.duration_seconds-title.start_time} step={.1} value={title.duration} onCommit={nextValue => updateTitle(title.id,{duration:Math.max(.1,Math.min(plan.duration_seconds-title.start_time,nextValue)),behind_subject:false})} /></label></div>
        <label className="flex gap-2 items-center"><input type="checkbox" checked={title.behind_subject} disabled={!!busy}
          onChange={e => { if(!e.target.checked){updateTitle(title.id,{behind_subject:false});return;}
            run('Preparing subject mask',async()=>{
              const clip=plan.clips.find(c=>c.id===title.source_clip_id);
              if(!clip || clip.media_type!=='video' || title.start_time<clip.start_time || title.start_time+title.duration>clip.start_time+clip.duration+.001)throw new Error('Keep text-behind-speaker within its source video clip.');
              const before=latest.current;
              const job=await creativeRequest<{job_id:string}>('/cinematic/prepare',{plan,clip_id:title.source_clip_id});
              setMaskJob(job.job_id);
              await waitCreativeJob(job.job_id,setBusy);
              if(before!==latest.current) throw new Error('The framing changed while preparing the mask. Please try again.');
              updateTitle(title.id,{behind_subject:true});
            });
          }} />Text behind speaker</label>
        <button className={button} onClick={() => onChange({...plan,cinematic_texts:plan.cinematic_texts?.filter(t=>t.id!==title.id)})}>Remove text</button>
      </div>)}
    </section>
    {busy && <p role="status">{busy}…</p>}
    {busy && maskJob && <button className={button} onClick={()=>void creativeRequest(`/creative/jobs/${maskJob}/cancel`,{}).catch(error=>setMessage(error.message))}>Cancel mask preparation</button>}
    {message && <p role="status" className="text-zinc-700 border-l-2 border-zinc-400 pl-2">{message}</p>}
  </div>;
}
