import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import PreviewPlayer from '../src/features/ai-editor/components/PreviewPlayer';

const root = createRoot(document.getElementById('root')!);
let props: any = { timelineClips: [], mediaItems: [], timelineTracks: [{ id: 'v', type: 'video' }],
  playheadPosition: 0, isPlaying: false, canvasWidth: 320, canvasHeight: 180, showControls: false };
(window as any).previewTest = {
  set(update: any) {
    props = { ...props, ...update };
    flushSync(() => root.render(<PreviewPlayer {...props} />));
  },
  pixel(x = 160, y = 90) {
    return [...document.querySelector('canvas')!.getContext('2d')!.getImageData(x, y, 1, 1).data];
  },
  unmount() { root.unmount(); },
};
(window as any).previewTest.set({});
