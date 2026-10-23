import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
const files = [];
function walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (/\.test\.tsx?$/.test(entry.name)) files.push(file);
  }
}
walk('src/features/ai-editor');
const result = spawnSync(process.execPath, ['--import', './scripts/editor-test-loader.mjs', '--test', '--test-concurrency=2', ...files], { stdio: 'inherit' });
process.exitCode = result.status ?? 1;
