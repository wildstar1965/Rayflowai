// One process per operation: credentials cannot bleed between judge requests.
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
let input = '';
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');

function revive(value) {
  if (value?.__blob) return new Blob([Buffer.from(value.__blob, 'base64')], { type: value.mimeType });
  if (value?.__bytes) return Buffer.from(value.__bytes, 'base64');
  if (Array.isArray(value)) return value.map(revive);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, revive(child)]));
  return value;
}

try {
  if (request.operation === 'gemini') {
    const { GoogleGenAI } = await import('@google/genai');
    const allowed = {
      models: ['generateContent', 'countTokens', 'embedContent', 'generateImages', 'editImage', 'upscaleImage', 'generateVideos', 'list', 'get'],
      operations: ['getVideosOperation', 'get'], files: ['upload', 'get', 'list', 'delete'],
    };
    const { namespace, method, params } = request.payload;
    if (!allowed[namespace]?.includes(method)) throw new Error('Unsupported Google SDK operation.');
    const client = new GoogleGenAI({ apiKey: request.credential });
    let result = await client[namespace][method](revive(params));
    if (method === 'list' && result && Symbol.asyncIterator in result) {
      const items = []; for await (const item of result) items.push(item); result = items;
    }
    // SDK response convenience properties live on prototypes; retain their values.
    if (result && !Array.isArray(result)) {
      const output = { ...result };
      for (const name of ['text', 'data', 'functionCalls', 'executableCode', 'codeExecutionResult']) {
        try { if (result[name] !== undefined) output[name] = result[name]; } catch { /* optional SDK getter */ }
      }
      result = output;
    }
    emit({ result });
  } else if (request.operation === 'surface-map') {
    const { runSurfaceMapProcess } = require('./surface-map-runtime.cjs');
    emit({ result: await runSurfaceMapProcess(request.payload) });
  } else if (request.operation === 'corridor-key') {
    const { runCorridorKeyProcess } = require('./corridor-key-runtime.cjs');
    emit({ result: await runCorridorKeyProcess(request.payload) });
  } else if (request.operation === 'export') {
    const { renderTimeline } = require('./ffmpeg-handler.cjs');
    const output = await renderTimeline(request.folder, request.payload.project, request.payload.settings,
      progress => emit({ progress: progress.percent || 0 }));
    emit({ result: { outputPath: output } });
  } else {
    throw new Error('Unsupported runtime operation.');
  }
} catch (error) {
  const message = String(error?.message || 'Runtime operation failed.');
  const clean = request.credential ? message.replaceAll(request.credential, '[redacted]') : message;
  emit({ error: clean.slice(0, 1000) });
  process.exitCode = 1;
}
