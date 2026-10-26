import type { TimelineClip, TimelineTrack } from '../types';

export interface AssistantTransform {
  clipId?: string;
  x?: number;
  y?: number;
  rotation?: number;
  relative?: boolean;
}

export function transformAssistantClip(clips: TimelineClip[], tracks: TimelineTrack[], selectedId: string | null, args: AssistantTransform) {
  const id = args.clipId || selectedId;
  const clip = clips.find(item => item.id === id);
  if (!clip) throw new Error('Select a clip before asking to move or rotate it.');
  const track = tracks.find(item => item.id === clip.trackId);
  if (!track || track.type !== 'video') throw new Error('Select a visual clip to move or rotate.');
  if (track.isLocked) throw new Error('Unlock the selected track before changing its clips.');
  const fields = ['x', 'y', 'rotation'] as const;
  if (!fields.some(field => args[field] !== undefined)) throw new Error('Specify a position or rotation.');
  for (const field of fields) {
    const value = args[field];
    if (value !== undefined && (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > (field === 'rotation' ? 360 : 100))) {
      throw new Error('Use finite positions within 100% and rotations within 360 degrees.');
    }
  }
  if ((args.x !== undefined || args.y !== undefined) && (clip.kenBurns?.enabled || clip.keyframes?.some(frame => frame.property === 'x' || frame.property === 'y'))) {
    throw new Error('Disable position animation before moving this clip. Its motion was preserved.');
  }
  const previous = clip.transform || { scale: 1, opacity: 1, position: { x: 50, y: 50 } };
  const position = { ...previous.position };
  for (const field of ['x', 'y'] as const) {
    if (args[field] === undefined) continue;
    const value = args[field] + (args.relative ? position[field] : 0);
    if (value < 0 || value > 100) throw new Error('This movement would place the clip outside the frame.');
    position[field] = value;
  }
  const rotation = args.rotation === undefined ? previous.rotation || 0
    : ((args.rotation + (args.relative ? previous.rotation || 0 : 0) + 180) % 360 + 360) % 360 - 180;
  const transform = { ...previous, position, rotation };
  return { clips: clips.map(item => item.id === id ? { ...item, transform } : item), transform };
}
