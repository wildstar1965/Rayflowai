import { readFile, writeFile } from 'node:fs/promises';
import postcss from 'postcss';

const location = new URL('../src/features/ai-editor/', import.meta.url);
const css = await readFile(new URL('upstream.css', location), 'utf8');
const root = postcss.parse(css);
root.walkAtRules('import', rule => rule.remove());
root.walkRules(rule => {
  if (rule.parent?.type === 'atrule' && /keyframes$/.test(rule.parent.name)) return;
  rule.selectors = rule.selectors.map(selector => {
    const normalized = selector.replace(/:root|\bhtml\b|\bbody\b/g, '.rayflow-editor');
    if (normalized.includes('.rayflow-editor')) return normalized;
    return `.rayflow-editor ${normalized}`;
  });
});
root.walkDecls('font-family', rule => { rule.value = 'Onest, system-ui, sans-serif'; });
await writeFile(new URL('editor.css', location), root.toString());
console.log('Scoped upstream editor CSS to the Rayflow workspace.');
