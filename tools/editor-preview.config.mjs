// Local diagnostic preview only. Production continues to use frontend/vite.config.ts.
// Reads existing upstream packages while npm downloads await approval; no source files are changed.
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const root = path.resolve(import.meta.dirname, '../frontend');
const require = createRequire(path.join(root, 'package.json'));
const { default: react } = await import(pathToFileURL(require.resolve('@vitejs/plugin-react')).href);
const source = process.env.RAYFLOW_EDITOR_SOURCE;
if (!source) throw new Error('Set RAYFLOW_EDITOR_SOURCE for a diagnostic preview.');
const dependencies = ['@google/genai', '@hocuspocus/provider', '@supabase/supabase-js', '@e965/xlsx',
  'mammoth', 'pdfjs-dist', 'react-markdown', 'reactflow', 'three', 'yjs'];
export default {
  root, plugins: [react()],
  optimizeDeps: { exclude: ['pdfjs-dist'] },
  resolve: { alias: dependencies.map(name => ({ find: name, replacement: path.join(source, 'node_modules', name) })),
    dedupe: ['react', 'react-dom'] },
  server: { fs: { allow: [root, path.join(source, 'node_modules')] },
    proxy: { '/api': { target: process.env.RAYFLOW_API_PROXY_TARGET, changeOrigin: true } } },
};
