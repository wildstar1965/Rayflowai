import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeProjectDocuments, ProjectMergeConflict } from './projectMerge.ts';

test('project merge retains independent clips, effects, and remote fields on later saves', () => {
  const base = { timelineClips: [{ id: 'a', start: 0, effects: { grade: 1, gain: 1 } }], storyBible: { title: 'Opening' } };
  const local = structuredClone(base);
  local.timelineClips[0].effects.grade = 2;
  const remote = structuredClone(base);
  remote.timelineClips[0].effects.gain = 0.5;
  remote.storyBible.title = 'Shared opening';
  const merged = mergeProjectDocuments(base, local, remote);
  assert.deepEqual(merged.timelineClips[0].effects, { grade: 2, gain: 0.5 });
  const next = structuredClone(local);
  next.timelineClips[0].start = 3;
  const savedAgain = mergeProjectDocuments(local, next, merged);
  assert.equal(savedAgain.storyBible.title, 'Shared opening');
  assert.equal(savedAgain.timelineClips[0].effects.gain, 0.5);
  assert.equal(savedAgain.timelineClips[0].start, 3);
});

test('project merge preserves additions and deletions but rejects delete-versus-edit', () => {
  const base = [{ id: 'a', start: 0 }, { id: 'b', start: 1 }];
  assert.deepEqual(mergeProjectDocuments(base, [base[0]], [...base, { id: 'c', start: 2 }]).map((item: any) => item.id), ['a', 'c']);
  assert.throws(() => mergeProjectDocuments(base, [base[0]], [base[0], { id: 'b', start: 3 }]), ProjectMergeConflict);
  assert.throws(() => mergeProjectDocuments({ filters: [1] }, { filters: [2] }, { filters: [3] }), ProjectMergeConflict);
});

test('project merge rejects conflicting track ordering and keeps metadata timestamps monotonic', () => {
  const base = ['a', 'b', 'c'].map(id => ({ id }));
  assert.throws(() => mergeProjectDocuments(base, [base[1], base[0], base[2]], [base[0], base[2], base[1]]), ProjectMergeConflict);
  assert.deepEqual(mergeProjectDocuments({ savedAt: '2026-01-01' }, { savedAt: '2026-01-02' }, { savedAt: '2026-01-03' }), { savedAt: '2026-01-03' });
});

test('save adapter retries a revision conflict and preserves merged remote fields on the next save', async () => {
  const { projectApi } = await import('./project.ts');
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { dispatchEvent: () => true } as any;
  let document = { name: 'Shared project', storyBible: { title: 'Opening', palette: 'ink' },
    collaboration: { lastModifiedBy: 'First', lastModifiedAt: '2026-01-01' } };
  let revision = 1;
  let puts = 0;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === 'PUT') {
      puts++;
      const body = JSON.parse(String(options.body));
      if (body.document_revision !== revision) return Response.json({ detail: 'Document changed' }, { status: 409 });
      document = body.project;
      revision++;
    }
    return Response.json({ id: 'merge-adapter-test', name: document.name, project: structuredClone(document), document_revision: revision });
  };
  try {
    await projectApi.loadProject({ folderPath: 'merge-adapter-test' });
    const local = structuredClone(document);
    local.storyBible.palette = 'jade';
    local.collaboration = { lastModifiedBy: 'First', lastModifiedAt: '2026-01-03' };
    document.storyBible.title = 'Remote opening';
    document.collaboration = { lastModifiedBy: 'Second', lastModifiedAt: '2026-01-02' };
    revision++;
    await projectApi.saveProject({ folderPath: 'merge-adapter-test', project: local, assets: [] });
    assert.equal(puts, 2);
    assert.deepEqual(document.storyBible, { title: 'Remote opening', palette: 'jade' });
    assert.equal(document.collaboration.lastModifiedBy, 'First');
    local.storyBible.palette = 'brass';
    await projectApi.saveProject({ folderPath: 'merge-adapter-test', project: local, assets: [] });
    assert.deepEqual(document.storyBible, { title: 'Remote opening', palette: 'brass' });
    await projectApi.writeProjectFile({ folderPath: 'merge-adapter-test', relativePath: 'project.json',
      data: JSON.stringify({ ...document, name: 'Restored cloud project' }), encoding: 'utf8' });
    const loaded = await projectApi.loadProject({ folderPath: 'merge-adapter-test' });
    assert.equal(loaded.project.name, 'Restored cloud project');
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow; }
});
