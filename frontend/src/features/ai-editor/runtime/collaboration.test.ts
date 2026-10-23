import test from 'node:test';
import assert from 'node:assert/strict';
import * as Y from 'yjs';
import { HostedCollaborationProvider } from './collaboration.ts';

test('hosted relay converges concurrent edits, retries failures and restores a reconnect', async () => {
  const original = globalThis.fetch;
  const updates = new Map<string, any>();
  let failNext = false;
  globalThis.fetch = async (_path, options) => {
    if (options?.method === 'POST') {
      if (failNext) { failNext = false; throw new Error('temporary outage'); }
      const body = JSON.parse(String(options.body));
      if (body.update) updates.set(body.update, { id: body.update, data: body.update });
      return Response.json({ ok: true });
    }
    return Response.json({ updates: [...updates.values()], presence: [] });
  };
  const documents = [new Y.Doc(), new Y.Doc(), new Y.Doc()];
  const providers = documents.map(document => new HostedCollaborationProvider({ document, projectId: 'shared', onStatus: () => {}, onAwarenessChange: () => {} }));
  try {
    await providers[0].connect(); await providers[1].connect();
    documents[0].getMap('clips').set('one', { start: 0, end: 2 });
    documents[1].getMap('clips').set('two', { start: 2, end: 4 });
    failNext = true;
    await assert.rejects(providers[0].flush(), /temporary outage/);
    await providers[0].flush(); await providers[1].flush();
    await providers[2].connect();
    assert.deepEqual(documents[2].getMap('clips').toJSON(), { one: { start: 0, end: 2 }, two: { start: 2, end: 4 } });
    documents[2].getMap('clips').set('three', { start: 4, end: 6 });
    providers[2].disconnect();
    await providers[2].flush();
    assert.equal(updates.size, 3, 'navigation must flush the final pending edit');
  } finally {
    for (const provider of providers) { provider.disconnect(); await provider.flush(); provider.destroy(); }
    for (const document of documents) document.destroy();
    globalThis.fetch = original;
  }
});
