import test from 'node:test';
import assert from 'node:assert/strict';
import { initializeWorkspace } from '../../../services/editorClient.ts';
import { uploadImages, uploadAudio } from '../../../services/api.ts';

test('hosted Studio uploads media directly to private Storage before adapting assets', async () => {
  const original = globalThis.fetch;
  const requests: string[] = [];
  globalThis.window = { dispatchEvent: () => true } as any;
  globalThis.fetch = async (input, options) => {
    const path = String(input); requests.push(path);
    assert.ok(!path.includes('/media/images') && !path.includes('/media/audio'), 'large media must not pass through Vercel API forwarding');
    if (path === '/api/session') return Response.json({ workspace_id: 'judge', storage: 'supabase', preferences: {} });
    if (path === '/api/editor/providers') return Response.json({ providers: [] });
    if (path === '/api/editor/assets/upload-ticket') return Response.json({ asset: { id: 'asset' }, upload: { url: 'https://storage.example/upload?token=scoped' } });
    if (path.startsWith('https://storage.example/')) {
      assert.equal(options?.method, 'PUT'); assert.ok(options?.body instanceof File);
      assert.ok(!new Headers(options?.headers).has('Authorization'));
      return new Response('{}');
    }
    if (path === '/api/editor/assets/asset/complete') return Response.json({ id: 'asset' });
    if (path === '/api/editor/assets/asset/studio') return Response.json({ filename: 'shared.png', url: '/api/uploads/shared.png' });
    throw new Error('Unexpected request ' + path);
  };
  try {
    await initializeWorkspace();
    assert.equal((await uploadImages([new File(['image'], 'image.png', { type: 'image/png' })]))[0].filename, 'shared.png');
    await uploadAudio(new File(['audio'], 'audio.wav', { type: 'audio/wav' }));
    assert.equal(requests.filter(path => path.startsWith('https://storage.example/')).length, 2);
  } finally { globalThis.fetch = original; }
});
