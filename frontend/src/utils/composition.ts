import type { VisualInsert } from '../types';

export function insertRect(ins: VisualInsert): [number, number, number, number] {
  if (ins.mode === 'cutaway' || ins.mode === 'background') return [0, 0, 1, 1];
  if (ins.mode === 'split') return [.5, 0, .5, 1];
  if (ins.position === 'top_left') return [.05, .08, .38, .24];
  if (ins.position === 'bottom_right') return [.57, .55, .38, .24];
  if (ins.position === 'center') return [.31, .32, .38, .24];
  return [.57, .08, .38, .24];
}

export function drawCover(ctx: CanvasRenderingContext2D, media: CanvasImageSource, sourceW: number,
  sourceH: number, x: number, y: number, width: number, height: number) {
  const scale = Math.max(width / sourceW, height / sourceH);
  const sw = width / scale, sh = height / scale;
  ctx.drawImage(media, (sourceW - sw) / 2, (sourceH - sh) / 2, sw, sh, x, y, width, height);
}
