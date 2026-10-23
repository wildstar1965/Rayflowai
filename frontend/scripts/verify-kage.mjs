import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('vendor/threeui/source-manifest.json', root), 'utf8'));

await Promise.all([...manifest.files, ...manifest.supportFiles].map(async ({ path, bytes, sha256 }) => {
  const content = await readFile(new URL(path, root));
  assert.equal(content.length, bytes, `${path}: byte count changed`);
  assert.equal(createHash('sha256').update(content).digest('hex'), sha256, `${path}: source hash changed`);
}));

const [registered, entry] = await Promise.all([
  readFile(new URL('vendor/threeui/src/shaders/landing-pages/LandingPages.tsx', root), 'utf8'),
  readFile(new URL('vendor/threeui/index.tsx', root), 'utf8'),
]);
const kageExport = /export function KageLandingPage\([^\n]+\) \{\n[\s\S]*?\n\}/;
assert.ok(registered.match(kageExport), 'Registered Kage export is missing');
assert.equal(entry.match(kageExport)?.[0], registered.match(kageExport)[0], 'Kage entry differs from registered source');

console.log(`Kage ${manifest.revision.slice(0, 12)}: all ${manifest.files.length} source/asset hashes and the component entry verified.`);
