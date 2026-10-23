import type { EditingPlan, SubtitleSegment } from '../types';

export function newCaptionInterval(plan: EditingPlan, time: number): {start_time:number;end_time:number} | null {
  let start=Math.max(0,Math.min(time,plan.duration_seconds-.01));
  for(const segment of [...(plan.subtitles||[])].sort((a,b)=>a.start_time-b.start_time)){
    if(segment.end_time<=start)continue;
    if(segment.start_time>start+.01)return {start_time:start,end_time:Math.min(start+2,segment.start_time,plan.duration_seconds)};
    start=segment.end_time;
  }
  return start<plan.duration_seconds-.009?{start_time:start,end_time:Math.min(start+2,plan.duration_seconds)}:null;
}

export function attachTranscript(segments: SubtitleSegment[], plan: EditingPlan, filename: string): SubtitleSegment[] {
  const clips = plan.clips.filter(c => c.media_type === 'video' && c.image_url.split('/').pop() === filename);
  if (!clips.length && /\.(mp4|mov|webm|avi|mkv)$/i.test(filename)) return [];
  return (clips.length ? clips : [null]).flatMap(clip => {
    const sourceStart = clip?.source_start || 0;
    const duration = clip?.duration ?? plan.duration_seconds;
    const offset = clip ? clip.start_time-sourceStart : 0;
    return segments.flatMap(segment => {
      const start = Math.max(sourceStart, segment.start_time), end = Math.min(sourceStart+duration, segment.end_time);
      if(end <= start)return [];
      const words = (segment.words || []).filter(w => w.end > start && w.start < end).map(w => ({...w,
        start:Math.max(start,w.start)+offset,end:Math.min(end,w.end)+offset}));
      return [{...segment,id:`${clip?.id || 'audio'}-${segment.id}`,start_time:start+offset,end_time:end+offset,
        text:words.length && words.length !== segment.words?.length ? words.map(w=>w.word).join(' ') : segment.text,
        words,source_clip_id:clip?.id,source_filename:filename,origin:'auto' as const}];
    });
  }).sort((a,b)=>a.start_time-b.start_time);
}

/** Regenerate one source while preserving manual edits and other caption sources. */
export function mergeSourceCaptions(plan: EditingPlan, generated: SubtitleSegment[], filename: string): SubtitleSegment[] {
  const preserved = (plan.subtitles || []).filter(s => s.origin !== 'auto' || s.source_filename !== filename);
  const fresh = generated.flatMap(segment => {
    let windows = [[segment.start_time, segment.end_time]];
    for (const existing of preserved) {
      windows = windows.flatMap(([start, end]) => {
        if (existing.end_time <= start || existing.start_time >= end) return [[start, end]];
        return [[start, Math.min(end, existing.start_time)], [Math.max(start, existing.end_time), end]].filter(([a,b]) => b > a);
      });
    }
    return windows.flatMap(([start, end], index) => {
      if (start === segment.start_time && end === segment.end_time) return [segment];
      const words = (segment.words || []).filter(w => w.end > start && w.start < end)
        .map(w => ({...w, start: Math.max(start, w.start), end: Math.min(end, w.end)}));
      if (!words.length) return [];
      return [{...segment, id: `${segment.id}-part-${index}`, start_time: start, end_time: end,
        text: words.map(w => w.word).join(' '), words}];
    });
  });
  return [...preserved, ...fresh].sort((a,b) => a.start_time - b.start_time);
}

export function editCaptionTiming(plan: EditingPlan, id: string, field: 'start_time' | 'end_time', value: number): EditingPlan {
  if(!Number.isFinite(value))return plan;
  const current = plan.subtitles?.find(s=>s.id===id);
  if(!current)return plan;
  const others=(plan.subtitles || []).filter(s=>s.id!==id);
  const before=Math.max(0,...others.filter(s=>s.start_time<current.start_time).map(s=>s.end_time));
  const after=Math.min(plan.duration_seconds,...others.filter(s=>s.start_time>=current.end_time).map(s=>s.start_time));
  const start=field==='start_time'?Math.max(before,Math.min(current.end_time-.01,value)):current.start_time;
  const end=field==='end_time'?Math.min(after,Math.max(start+.01,value)):current.end_time;
  return {...plan,subtitles:plan.subtitles?.map(s=>s.id===id?{...s,start_time:start,end_time:end,origin:'manual',
    words:s.words?.filter(w=>w.end>start&&w.start<end).map(w=>({...w,start:Math.max(start,w.start),end:Math.min(end,w.end)}))}:s)};
}
