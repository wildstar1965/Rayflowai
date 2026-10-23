import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const output = new URL('public/landing-pages/kage.html', root);

export async function rayflowDocument() {
  let source = await readFile(new URL('vendor/threeui/upstream/kage.html', root), 'utf8');
  // Extract the existing preloader presentation for use by the editor as well.
  // The landing page retains its own scene-readiness and progress lifecycle.
  source = source.replace(/\.pre-in\{[^]*?\.pre-meta b\{[^}]*\}/, '');
  source = source.replace('</head>', '<link rel="stylesheet" href="./rayflow-preloader.css">\n</head>');
  source = source.replace(/(<div class="pre-mark">)\s*<svg[^]*?<\/svg>/, '$1<img src="./rayflow-mark.svg" alt="">');
  const copy = JSON.parse(await readFile(new URL('src/content/rayflowLandingCopy.json', root), 'utf8'));
  for (const { from, to, count } of copy.literals) {
    assert.equal(source.split(from).length - 1, count, `Rayflow source anchor changed: ${from}`);
    source = source.replaceAll(from, to);
  }

  // Keep all markup, attributes, styles, scene code, and asset URLs in place.
  // Replace only authored text nodes outside script/style blocks.
  const used = new Set();
  const escape = (text) => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  source = source.replace(/(<script\b[^>]*>[\s\S]*?<\/script>|<style\b[^>]*>[\s\S]*?<\/style>|<!--[^]*?-->)|>([^<>]+)</g,
    (whole, protectedBlock, text) => {
      if (protectedBlock) return whole;
      const key = text.trim().replace(/\s+/g, ' ');
      if (!Object.hasOwn(copy.text, key)) return whole;
      used.add(key);
      return `>${text.match(/^\s*/)[0]}${escape(copy.text[key])}${text.match(/\s*$/)[0]}<`;
    });
  for (const key of Object.keys(copy.text)) assert.ok(used.has(key), `Unused Rayflow copy: ${key}`);
  return source;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const document = await rayflowDocument();
  if (process.argv.includes('--check')) {
    assert.equal(await readFile(output, 'utf8'), document, 'Run npm run brand:rayflow to refresh the branded page');
    console.log('Rayflow copy, banner, and source structure verified.');
  } else {
    await writeFile(output, document);
    console.log('Updated the existing landing page with Rayflow copy and banner.');
  }
}
