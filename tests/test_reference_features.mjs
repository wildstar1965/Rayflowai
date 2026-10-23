import test from 'node:test';
import assert from 'node:assert/strict';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';
import { readFileSync } from 'node:fs';
const load = async path => import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText).toString('base64'));
const { regroupCaptions, splitWordsIntoSubtitleSegments } = await load('../frontend/src/utils/smartCaptions.ts');
const { buildOpenTimelineIOFromTimeline } = await load('../frontend/src/vendor/aivpe/openTimelineIOExport.ts');

test('smart phrases preserve real word timings, style and source while splitting long captions', () => {
  const words = Array.from({ length: 24 }, (_, index) => ({ word: `word${index}`, start: index * .4, end: index * .4 + .3, emphasis: index === 2 }));
  const source = { id: 'caption', text: 'long transcript', start_time: 0, end_time: 10, words, source_filename: 'speech.mp4', style: { font_size: 42 } };
  const result = regroupCaptions([source]);
  assert.ok(result.length > 1);
  assert.deepEqual(result.flatMap(segment => segment.words), words);
  assert.ok(result.every(segment => segment.style === source.style && segment.source_filename === 'speech.mp4'));
  assert.deepEqual(source.words, words);
});
test('grouping clamps invalid boundaries and rejects captions without measured words', () => {
  assert.deepEqual(splitWordsIntoSubtitleSegments([{ word: 'outside', start: 9, end: 10 }], 0, 2), []);
  assert.throws(() => regroupCaptions([{ id: 'x', words: [] }]), /word-timed/);
});
test('OTIO export preserves source trim and actual gaps, omits muted tracks', () => {
  const data = JSON.parse(buildOpenTimelineIOFromTimeline({ mediaItems: [{ id: 'm', name: 'video', type: 'video', url: 'https://example.test/video.mp4', duration: 10 }], timelineClips: [{ id: 'c', mediaId: 'm', trackId: 'v', start: 1, end: 3, sourceIn: 4 }], fps: 30 }));
  const children = data.tracks.children[0].children;
  assert.equal(children[0].OTIO_SCHEMA, 'Gap.1');
  assert.equal(children[0].source_range.duration.value, 30);
  assert.equal(children[1].source_range.start_time.value, 120);
  assert.equal(children[1].source_range.duration.value, 60);
  assert.throws(() => buildOpenTimelineIOFromTimeline({ mediaItems: [], timelineClips: [] }), /No exportable/);
});
