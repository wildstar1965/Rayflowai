import test from 'node:test';
import assert from 'node:assert/strict';
import { splitTimelineClip } from './splitClip';
import type { TimelineClip } from '../types';

test('split preserves source continuity, easing, motion and only the original outgoing transition', () => {
  const clip = { id: 'a', start: 2, end: 4, speed: 2, sourceIn: 1, sourceOut: 5, duration: 4,
    transitionOut: { type: 'Cross Fade', duration: .4 },
    keyframes: [{ time: 0, value: 1, property: 'scale', easing: 'linear' }, { time: 4, value: 2, property: 'scale', easing: 'ease-in' }],
    kenBurns: { enabled: true, start: { x: 0, y: 0, scale: 1 }, end: { x: 100, y: 100, scale: 2 } } } as TimelineClip;
  const [first, second] = splitTimelineClip(clip, 3, 'b')!;
  assert.equal(first.sourceOut, second.sourceIn);
  assert.equal(first.end, second.start);
  assert.equal(first.transitionOut, undefined);
  assert.deepEqual(second.transitionOut, clip.transitionOut);
  assert.deepEqual(second.keyframes?.map(key => key.time), [-2, 2]);
  assert.deepEqual(first.kenBurns?.end, second.kenBurns?.start);
  assert.equal(clip.keyframes?.[0].time, 0);
  assert.equal(splitTimelineClip(clip, 2.001, 'b'), null);
  assert.equal(splitTimelineClip(clip, 4, 'b'), null);
});
