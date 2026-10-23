import { registerHooks, createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import ts from 'typescript';
const localPackages = process.env.RAYFLOW_EDITOR_SOURCE ? createRequire(path.join(process.env.RAYFLOW_EDITOR_SOURCE, 'package.json')) : null;
registerHooks({
  resolve(specifier, context, nextResolve) {
    try { return nextResolve(specifier, context); }
    catch (error) {
      if (specifier.startsWith('.') && context.parentURL?.startsWith('file:')) {
        const base = fileURLToPath(new URL(specifier, context.parentURL));
        for (const suffix of ['.ts', '.tsx', '/index.ts']) {
          if (existsSync(base + suffix)) return { url: pathToFileURL(base + suffix).href, shortCircuit: true };
        }
      }
      if (localPackages && !specifier.startsWith('.') && !specifier.startsWith('node:')) {
        return { url: pathToFileURL(localPackages.resolve(specifier)).href, shortCircuit: true };
      }
      throw error;
    }
  },
  load(url, context, nextLoad) {
    if (/\.tsx?$/.test(url) && !url.includes('/node_modules/')) {
      const output = ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { fileName: fileURLToPath(url), compilerOptions: {
        target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX,
      } });
      return { format: 'module', source: output.outputText, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});
