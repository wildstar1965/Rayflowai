import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const ts = require('typescript');
const source = await readFile(new URL('../frontend/src/utils/timeline.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { reorderClips, reconcileTransitions, recalculateTimeline, uploadedClip } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));

test('Video upload, initialization and reordering retain precise full source ranges', () => {
  const videos = [121.23333333333333, 10.01001, 0.06666666666666667].map((duration, i) =>
    uploadedClip({ filename: `${i}.mp4`, original_name: `${i}.mp4`, url: `/api/uploads/${i}.mp4`,
      media_type: 'video', duration }, 0));
  const image = uploadedClip({ filename: 'a.png', url: '/api/uploads/a.png', media_type: 'image' }, 0);
  assert.equal(image.duration, 2.5);
  const original = { clips: [...videos, image], transitions: [], duration_seconds: 0 };
  const initialized = recalculateTimeline(original.clips, [], original);
  const reordered = recalculateTimeline(reorderClips(initialized.clips, videos[0].id, image.id, 'after'), [], initialized);
  for (const video of videos) {
    const clip = reordered.clips.find(c => c.id === video.id);
    assert.equal(clip.duration, video.source_duration);
    assert.equal(clip.source_start, 0);
  }
  const trimmed = { ...reordered.clips[0], duration: .4137, source_start: .237 };
  const edited = recalculateTimeline([trimmed, ...reordered.clips.slice(1)], [], reordered);
  assert.equal(edited.clips[0].duration, .4137);
  assert.equal(edited.clips[0].source_start, .237);
  assert.equal(edited.clips[0].source_duration, trimmed.source_duration);
  assert.deepEqual(recalculateTimeline(edited.clips, [], edited), edited);
  assert.throws(() => uploadedClip({media_type: 'video', original_name: 'unknown.mp4'}, 0), /source duration/);
});

test('Reorder first clip to last position', () => {
  const clips = [
    { id: 'c1', duration: 2.0 },
    { id: 'c2', duration: 2.0 },
    { id: 'c3', duration: 2.0 },
    { id: 'c4', duration: 2.0 }
  ];
  const reordered = reorderClips(clips, 'c1', 'c4', 'after');
  assert.deepEqual(reordered.map(c => c.id), ['c2', 'c3', 'c4', 'c1']);
});

test('Reorder last clip to first position', () => {
  const clips = [
    { id: 'c1', duration: 2.0 },
    { id: 'c2', duration: 2.0 },
    { id: 'c3', duration: 2.0 },
    { id: 'c4', duration: 2.0 }
  ];
  const reordered = reorderClips(clips, 'c4', 'c1', 'before');
  assert.deepEqual(reordered.map(c => c.id), ['c4', 'c1', 'c2', 'c3']);
});

test('Reorder clip one position left and right', () => {
  const clips = [
    { id: 'c1', duration: 2.0 },
    { id: 'c2', duration: 2.0 },
    { id: 'c3', duration: 2.0 },
    { id: 'c4', duration: 2.0 }
  ];
  // Move c2 right (after c3)
  const movedRight = reorderClips(clips, 'c2', 'c3', 'after');
  assert.deepEqual(movedRight.map(c => c.id), ['c1', 'c3', 'c2', 'c4']);

  // Move c3 left (before c2)
  const movedLeft = reorderClips(clips, 'c3', 'c2', 'before');
  assert.deepEqual(movedLeft.map(c => c.id), ['c1', 'c3', 'c2', 'c4']);
});

test('Reorder mixed images and video clips', () => {
  const clips = [
    { id: 'img1', media_type: 'image', duration: 2.0 },
    { id: 'vid1', media_type: 'video', duration: 4.5 },
    { id: 'img2', media_type: 'image', duration: 3.0 }
  ];
  const reordered = reorderClips(clips, 'vid1', 'img1', 'before');
  assert.deepEqual(reordered.map(c => c.id), ['vid1', 'img1', 'img2']);
  assert.equal(reordered[0].media_type, 'video');
  assert.equal(reordered[1].media_type, 'image');
});

test('Reconcile transitions: preserves unaffected transitions and removes invalid endpoints', () => {
  const clips = [
    { id: 'c1', duration: 2.0 },
    { id: 'c2', duration: 2.0 },
    { id: 'c3', duration: 2.0 },
    { id: 'c4', duration: 2.0 }
  ];
  const transitions = [
    { id: 't1', from_clip_id: 'c1', to_clip_id: 'c2', type: 'crossfade', duration: 0.5, enabled: true },
    { id: 't2', from_clip_id: 'c2', to_clip_id: 'c3', type: 'dip_black', duration: 0.4, enabled: true },
    { id: 't3', from_clip_id: 'c3', to_clip_id: 'c4', type: 'fade_in', duration: 0.5, enabled: true }
  ];

  // Move c1 to after c4: new order is ['c2', 'c3', 'c4', 'c1']
  const reordered = reorderClips(clips, 'c1', 'c4', 'after');
  const reconciled = reconcileTransitions(reordered, transitions);

  assert.equal(reconciled.length, 3);
  // c2 -> c3: unaffected, preserved!
  assert.equal(reconciled[0].from_clip_id, 'c2');
  assert.equal(reconciled[0].to_clip_id, 'c3');
  assert.equal(reconciled[0].type, 'dip_black');
  assert.equal(reconciled[0].duration, 0.4);

  // c3 -> c4: unaffected, preserved!
  assert.equal(reconciled[1].from_clip_id, 'c3');
  assert.equal(reconciled[1].to_clip_id, 'c4');
  assert.equal(reconciled[1].type, 'fade_in');

  // c4 -> c1: newly created boundary, does NOT inherit old t1 crossfade
  assert.equal(reconciled[2].from_clip_id, 'c4');
  assert.equal(reconciled[2].to_clip_id, 'c1');
  assert.equal(reconciled[2].type, 'none');

  // Old t1 (c1 -> c2) is purged completely
  assert.ok(!reconciled.some(t => t.from_clip_id === 'c1' && t.to_clip_id === 'c2'));
});

test('Reconcile transitions: clamps duration when clip is trimmed', () => {
  const clips = [
    { id: 'c1', duration: 0.4 }, // trimmed down to 0.4s
    { id: 'c2', duration: 2.0 }
  ];
  const transitions = [
    { id: 't1', from_clip_id: 'c1', to_clip_id: 'c2', type: 'crossfade', duration: 1.0, enabled: true }
  ];
  const reconciled = reconcileTransitions(clips, transitions);
  assert.equal(reconciled.length, 1);
  // Max duration should be min(0.4, 2.0) - 0.1 = 0.3s
  assert.ok(reconciled[0].duration <= 0.3);
});
