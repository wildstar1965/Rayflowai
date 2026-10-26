import test from 'node:test';
import assert from 'node:assert/strict';
import { transformAssistantClip } from './assistantTransform.ts';
import type { TimelineClip, TimelineTrack } from '../types';

const tracks = [{ id: 'v', type: 'video', isLocked: false }] as TimelineTrack[];
const clips = [{ id: 'a', trackId: 'v', start: 0, end: 4, transform: { scale: .8, opacity: .7, position: { x: 50, y: 50 }, rotation: 30 } }] as TimelineClip[];

test('relative moves and rotations preserve other clip properties and input history', () => {
  const result = transformAssistantClip(clips, tracks, 'a', { x: -5, rotation: 90, relative: true });
  assert.deepEqual(result.transform, { scale: .8, opacity: .7, position: { x: 45, y: 50 }, rotation: 120 });
  assert.equal(result.clips[0].end, 4);
  assert.equal(clips[0].transform?.rotation, 30);
  const reset = transformAssistantClip(result.clips, tracks, 'a', { x: 50, y: 50, rotation: 0 });
  assert.equal(reset.transform.rotation, 0);
  assert.equal(reset.transform.position.x, 50);
});

test('selection, locks, invalid numbers and animated position cannot silently change', () => {
  assert.throws(() => transformAssistantClip(clips, tracks, null, { rotation: 90 }), /Select/);
  assert.throws(() => transformAssistantClip(clips, [{ ...tracks[0], isLocked: true }], 'a', { rotation: 90 }), /Unlock/);
  for (const args of [{ rotation: NaN }, { x: 60, relative: true }, {}]) assert.throws(() => transformAssistantClip(clips, tracks, 'a', args));
  const animated = [{ ...clips[0], keyframes: [{ property: 'x', time: 0, value: 50 }] }] as TimelineClip[];
  assert.throws(() => transformAssistantClip(animated, tracks, 'a', { x: 40 }), /animation/);
  assert.equal(transformAssistantClip(animated, tracks, 'a', { rotation: -90 }).transform.rotation, -90);
});
