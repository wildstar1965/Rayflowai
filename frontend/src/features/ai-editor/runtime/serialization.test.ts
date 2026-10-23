import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeProjectValue, decodeProjectValue, replaceProjectReferences } from './serialization.ts';

test('LUT data and project metadata survive JSON archive serialization', () => {
  const original = { filters: { customLut: { data: new Float32Array([0, .25, 1]) } }, metadata: { future: ['preserved'] } };
  const decoded = decodeProjectValue(JSON.parse(JSON.stringify(encodeProjectValue(original))));
  assert.deepEqual(decoded, original);
  assert.ok(decoded.filters.customLut.data instanceof Float32Array);
});

test('relinking changes exact media references without editing scripts or labels', () => {
  const original = { media: ['old.png'], script: 'A scene about old.png', label: 'old' };
  assert.deepEqual(replaceProjectReferences(original, new Map([['old.png', 'new.png']])),
    { media: ['new.png'], script: 'A scene about old.png', label: 'old' });
  assert.equal(original.media[0], 'old.png');
});

test('malformed typed arrays fail explicitly', () => {
  assert.throws(() => decodeProjectValue({ __rayflowTypedArray: 'Function', values: [1] }), /unsupported/);
  assert.throws(() => decodeProjectValue({ __rayflowTypedArray: 'Float32Array', values: ['bad'] }), /unsupported/);
});
