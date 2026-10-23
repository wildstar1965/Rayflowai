import test from 'node:test';
import assert from 'node:assert/strict';
import { initializeWorkspace } from '../../../services/editorClient.ts';
import { editorFetch } from './transport.ts';

test('upstream CORS wrappers route provider requests through owned jobs without contacting a public proxy', async () => {
  const previousFetch = globalThis.fetch;
  const storage = new Map<string, string>();
  globalThis.window = { location: new URL('https://rayflow.test'), dispatchEvent: () => true } as any;
  globalThis.sessionStorage = { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) } as any;
  const providers = [
    ['replicate', 'api.replicate.com'], ['fal', 'queue.fal.run'], ['runway', 'api.dev.runwayml.com'], ['xai', 'api.x.ai'],
  ];
  const submissions: any[] = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    assert.ok(path.startsWith('/api/'), `Unexpected outbound request: ${path}`);
    if (path === '/api/session') return Response.json({ workspace_id: 'judge-one', preferences: {} });
    if (path === '/api/editor/providers') return Response.json({ providers: providers.map(([id, host]) => ({ id, configured: true, hosts: [host] })) });
    if (path === '/api/editor/jobs') { submissions.push(JSON.parse(String(init?.body))); return Response.json({ id: 'job' }); }
    if (path === '/api/editor/jobs/job') return Response.json({ status: 'completed', result: { status: 200, content_type: 'application/json', text: '{"ok":true}' } });
    throw new Error('Unexpected request');
  };
  try {
    await initializeWorkspace();
    for (const [provider, host] of providers) {
      const response = await editorFetch('https://corsproxy.io/?' + encodeURIComponent(`https://${host}/test`), {
        method: 'POST', body: '{"prompt":"test"}', headers: { Authorization: 'Bearer rayflow-managed:configured' },
      });
      assert.deepEqual(await response.json(), { ok: true });
      assert.equal(submissions.at(-1).payload.provider, provider);
      assert.equal(submissions.at(-1).payload.url, `https://${host}/test`);
      assert.equal(submissions.at(-1).kind, 'provider');
    }
    assert.equal(storage.size, 0);
  } finally { globalThis.fetch = previousFetch; }
});
