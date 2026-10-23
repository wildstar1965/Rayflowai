export interface MediaItem {
  id: string; name: string; type: 'video' | 'image' | 'audio';
  url: string; sourceUrl?: string; originUrl?: string; duration?: number;
}
export interface TimelineClip {
  id: string; mediaId: string; trackId: string; start: number; end: number;
  sourceIn?: number; sourceOut?: number; duration?: number; speed?: number; blendMode?: string;
}
export interface TimelineTrack { id: string; type: 'video' | 'audio'; isMuted?: boolean; isSolo?: boolean; name?: string }
