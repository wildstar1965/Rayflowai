import type { EditingPlan, UploadedAudio } from '../types';
import { buildOpenTimelineIOFromTimeline } from '../vendor/aivpe/openTimelineIOExport';
import type { MediaItem, TimelineClip } from '../vendor/aivpe/types';

export function exportTimeline(plan: EditingPlan, projectName: string, audio: UploadedAudio | null, resolveUrl: (url: string) => string) {
  if (!plan.clips.length) throw new Error('Add media to the timeline before exporting.');
  const mediaItems: MediaItem[] = [];
  const timelineClips: TimelineClip[] = [];
  for (const clip of plan.clips) {
    if (!Number.isFinite(clip.duration) || clip.duration <= 0) throw new Error('Every clip must have a positive duration.');
    mediaItems.push({ id: clip.id, name: clip.image_url.split('/').pop() || clip.id, type: clip.media_type || 'image', url: resolveUrl(clip.image_url), duration: (clip.source_start || 0) + clip.duration });
    timelineClips.push({ id: clip.id, mediaId: clip.id, trackId: 'video', start: clip.start_time, end: clip.start_time + clip.duration, sourceIn: clip.source_start || 0, duration: clip.duration });
  }
  if (audio) {
    mediaItems.push({ id: 'soundtrack', name: audio.original_name, type: 'audio', url: resolveUrl(audio.url), duration: plan.duration_seconds });
    timelineClips.push({ id: 'soundtrack', mediaId: 'soundtrack', trackId: 'audio', start: 0, end: plan.duration_seconds });
  }
  const dimensions = plan.aspect_ratio === '16:9' ? [1920, 1080] : plan.aspect_ratio === '1:1' ? [1080, 1080] : [1080, 1920];
  const result = JSON.parse(buildOpenTimelineIOFromTimeline({ projectName, fps: 30, width: dimensions[0], height: dimensions[1], mediaItems, timelineClips }));
  result.metadata.rayflow = { plan, notice: 'Cut timing and media references are portable. Rayflow captions, grading, transitions, overlays and sound processing are preserved in metadata; use MP4 export for their rendered appearance.' };
  return JSON.stringify(result, null, 2);
}

export function downloadTimeline(contents: string, projectName: string) {
  const url = URL.createObjectURL(new Blob([contents], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url; link.download = `${projectName.replace(/[^a-z0-9 _-]/gi, '-').slice(0, 80) || 'rayflow'}.otio`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
