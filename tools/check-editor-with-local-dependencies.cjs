// Diagnostic-only: resolve already installed upstream libraries without downloading,
// installing, modifying that checkout, or changing production module resolution.
const ts = require('../frontend/node_modules/typescript');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '../frontend');
process.chdir(root);
const upstream = process.argv[2];
if (!upstream) throw new Error('Supply the read-only upstream checkout for diagnostics.');
const config = ts.readConfigFile(path.join(root, 'tsconfig.app.json'), ts.sys.readFile);
const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, root);
const host = ts.createCompilerHost(parsed.options);
host.resolveModuleNames = (names, containingFile) => names.map(name => {
  if (name === 'react' || name.startsWith('react/')) {
    return ts.resolveModuleName(name, path.join(root, 'src/__diagnostic__.ts'), parsed.options, host).resolvedModule;
  }
  const normal = ts.resolveModuleName(name, containingFile, parsed.options, host).resolvedModule;
  if (normal || name.startsWith('.')) return normal;
  return ts.resolveModuleName(name, path.join(upstream, 'src/__diagnostic__.ts'), parsed.options, host).resolvedModule;
});
const program = ts.createProgram(parsed.fileNames, parsed.options, host);
const diagnostics = ts.getPreEmitDiagnostics(program);
const rendered = ts.formatDiagnostics(diagnostics, { getCanonicalFileName: p => p, getCurrentDirectory: () => root, getNewLine: () => '\n' });
fs.writeFileSync(path.resolve(__dirname, '../test_artifacts/editor-types.txt'), rendered);
console.log(`${diagnostics.length} diagnostics; see test_artifacts/editor-types.txt`);
process.exitCode = diagnostics.length ? 1 : 0;
