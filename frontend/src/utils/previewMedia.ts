// Each timeline occurrence owns its decoder. A seek changes currentTime before
// the browser has decoded that frame, so readyState alone is not sufficient.
const playback = new WeakMap<HTMLMediaElement, boolean>();

export function syncPreviewMedia(media: HTMLMediaElement, target: number, playing: boolean, speed = 1): boolean {
  const wasPlaying = playback.get(media);
  playback.set(media, playing);
  media.playbackRate = speed;
  if (!playing && !media.paused) media.pause();
  if (media.readyState < 1) return false;
  const end = Number.isFinite(media.duration) ? Math.max(0, media.duration - 0.000001) : Infinity;
  target = Math.max(0, Math.min(target, end));
  const tolerance = playing && wasPlaying === true ? 0.12 : 0.00001;
  if (media.seeking) return false;
  if (Math.abs(media.currentTime - target) > tolerance) {
    media.currentTime = target;
    return false;
  }
  if (media.readyState < 2) return false;
  if (playing && media.paused) void media.play().catch(() => {});
  return true;
}

export function releasePreviewMedia(media: HTMLMediaElement) {
  media.onloadeddata = media.onloadedmetadata = media.onseeked = media.oncanplay = media.onerror = null;
  media.pause();
  media.removeAttribute('src');
  media.load();
  playback.delete(media);
}
