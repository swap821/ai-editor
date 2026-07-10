import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// repoMapStore fetches on module load (top-level `if (typeof window !== 'undefined')`
// block), so fetch must be stubbed BEFORE the module is imported. Using
// vi.resetModules() + dynamic import per test gives each test a fresh module
// instance with a controlled fetch response. cognitionBus must be
// re-imported dynamically too (AFTER the same resetModules() call) so
// publishCognition talks to the SAME bus instance repoMapStore subscribed
// to -- a static top-level import would resolve to the pre-reset singleton.
async function loadStore(fetchImpl: typeof fetch) {
  vi.resetModules();
  vi.stubGlobal('fetch', fetchImpl);
  const store = await import('./repoMapStore');
  const bus = await import('./cognitionBus');
  return { store, bus };
}

describe('repoMapStore', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('starts empty and fills from a real fetch of the project tree (no hardcoded mock files)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { name: 'main.py', path: '/repo/main.py', type: 'file', status: 'normal' },
        { name: 'src', path: '/repo/src', type: 'directory', children: [] },
      ],
    });
    const { store } = await loadStore(fetchMock as unknown as typeof fetch);

    // Flush the fire-and-forget fetchInitialFiles() microtask chain.
    await Promise.resolve();
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/files/tree'),
      expect.objectContaining({ credentials: 'include' })
    );
    const state = store.getRepoMapState();
    expect(state.activeFiles).toHaveLength(1);
    expect(state.activeFiles[0]).toMatchObject({ name: 'main.py', path: '/repo/main.py', status: 'idle', errorCount: 0 });
    // None of the old hardcoded mock filenames leak into real state.
    expect(state.activeFiles.some((f) => f.path === '/src/main.jsx')).toBe(false);
  });

  it('normalizes an unrecognized backend status ("normal") to idle rather than passing it through', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'a.py', path: '/repo/a.py', type: 'file', status: 'normal' }],
    });
    const { store } = await loadStore(fetchMock as unknown as typeof fetch);
    await Promise.resolve();
    await Promise.resolve();

    expect(store.getRepoMapState().activeFiles[0].status).toBe('idle');
  });

  it('leaves activeFiles empty (not fake data) when the backend is unreachable', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network down'));
    const { store } = await loadStore(fetchMock as unknown as typeof fetch);
    await Promise.resolve();
    await Promise.resolve();

    expect(store.getRepoMapState().activeFiles).toEqual([]);
  });

  it('leaves activeFiles empty when the backend responds with a non-OK status', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500 });
    const { store } = await loadStore(fetchMock as unknown as typeof fetch);
    await Promise.resolve();
    await Promise.resolve();

    expect(store.getRepoMapState().activeFiles).toEqual([]);
  });

  describe('live file_tree cognition events', () => {
    let store: Awaited<ReturnType<typeof loadStore>>['store'];
    let bus: Awaited<ReturnType<typeof loadStore>>['bus'];

    beforeEach(async () => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
      ({ store, bus } = await loadStore(fetchMock as unknown as typeof fetch));
      await Promise.resolve();
      await Promise.resolve();
    });

    it('replaces activeFiles when a real file_tree event arrives (forward-compat path)', () => {
      bus.publishCognition({
        type: 'file_tree',
        source: 'test',
        data: {
          tree: [
            { name: 'x.py', path: '/repo/x.py', type: 'file', status: 'editing', errorCount: 1 },
          ],
        },
      });

      expect(store.getRepoMapState().activeFiles).toEqual([
        { name: 'x.py', path: '/repo/x.py', status: 'editing', errorCount: 1 },
      ]);
    });

    it('notifies subscribers on live updates', () => {
      const seen: unknown[] = [];
      const unsub = store.subscribeRepoMap((s) => seen.push(s.activeFiles.length));
      bus.publishCognition({
        type: 'file_tree',
        source: 'test',
        data: { tree: [{ name: 'y.py', path: '/repo/y.py', type: 'file' }] },
      });
      unsub();
      expect(seen[seen.length - 1]).toBe(1);
    });
  });
});
