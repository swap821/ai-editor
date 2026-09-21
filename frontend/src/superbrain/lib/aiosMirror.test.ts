import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { startMirrorClient, stopMirrorClient } from './aiosMirror';
import { useMirrorStore } from './mirrorStore';
import { publishCognition } from './cognitionBus';
vi.mock('./cognitionBus', () => ({ publishCognition: vi.fn() }));
vi.mock('./aiosAdapter', () => ({ humanizeRedactionMarkers: (value: string) => value }));

const snapshot = (id = 4) => ({ status: 'online', state: 'measured', last_event_id: id, phase: 'idle', active_workers: [], active_missions: [], active_castes: [] });
const response = (body: unknown, ok = true) => ({ ok, status: ok ? 200 : 503, json: async () => body }) as Response;
type FakeSource = { onopen: (() => void) | null; onerror: (() => void) | null; onmessage: ((event: { data: string; lastEventId: string }) => void) | null; close: ReturnType<typeof vi.fn>; listeners: Record<string, (event: { data: string }) => void>; addEventListener: ReturnType<typeof vi.fn> };
let sources: FakeSource[];
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks(); sources = [];
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(snapshot())));
  vi.stubGlobal('EventSource', vi.fn(function () {
    const s: FakeSource = { onopen: null, onerror: null, onmessage: null, close: vi.fn(), listeners: {}, addEventListener: vi.fn((type, listener) => { s.listeners[type] = listener; }) };
    sources.push(s); return s;
  }));
});
afterEach(() => { stopMirrorClient(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it('carries operator credentials on both transports and a snapshot watermark', async () => {
  await startMirrorClient();
  expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/mirror/snapshot', expect.objectContaining({ credentials: 'include', signal: expect.any(AbortSignal) }));
  expect(EventSource).toHaveBeenCalledWith('http://localhost:8000/api/v1/mirror/stream?last_event_id=4', { withCredentials: true });
});
it('connection opening never promotes a snapshot to a continuously fresh projection', async () => {
  await startMirrorClient(); sources[0].onopen!();
  expect(useMirrorStore.getState()).toMatchObject({ connection: 'connected', projection: 'snapshot' });
  expect(useMirrorStore.getState().status).not.toBe('online');
});
it('only promotes the mirror after sync_complete closes the snapshot cursor', async () => {
  await startMirrorClient(); sources[0].onopen!();
  expect(useMirrorStore.getState()).toMatchObject({ projection: 'snapshot', status: 'stale' });
  sources[0].listeners.sync_complete({ data: '{"cursor":4}' });
  expect(useMirrorStore.getState()).toMatchObject({ projection: 'fresh', status: 'online', lastEventId: 4 });
});
it('invalid snapshot remains unavailable even when the stream opens', async () => {
  vi.mocked(fetch).mockResolvedValue(response({ history: [] }));
  await startMirrorClient(); sources[0].onopen!();
  expect(useMirrorStore.getState()).toMatchObject({ connection: 'connected', projection: 'unavailable', snapshotReceivedAt: null });
});
it('concurrent starts share one snapshot and source', async () => {
  await Promise.all([startMirrorClient(), startMirrorClient()]);
  expect(fetch).toHaveBeenCalledTimes(1); expect(sources).toHaveLength(1);
});
it('stopping during a snapshot fetch prevents a late connection or state update', async () => {
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  const starting = startMirrorClient(); stopMirrorClient(); finish(response(snapshot())); await starting;
  expect(sources).toHaveLength(0); expect(useMirrorStore.getState().snapshotReceivedAt).toBeNull();
});
it('gap recovery closes the old source and reconciles a fresh snapshot before reopening', async () => {
  await startMirrorClient(); const old = sources[0];
  vi.mocked(fetch).mockResolvedValue(response(snapshot(9)));
  old.listeners.snapshot_required({ data: '{"reason":"replay_gap"}' });
  expect(old.close).toHaveBeenCalled();
  old.onmessage!({ data: JSON.stringify({ eventType: 'worker.started', payload: { workerId: 'old' } }), lastEventId: '99' });
  await vi.advanceTimersByTimeAsync(0);
  expect(useMirrorStore.getState().lastEventId).toBe(9);
  expect(useMirrorStore.getState().activeWorkers).toEqual([]);
  expect(sources).toHaveLength(2);
});
it('replayed events restore once and never reenact work without a live barrier', async () => {
  await startMirrorClient();
  const message = { data: JSON.stringify({ schemaVersion: '1', eventType: 'worker.started', payload: { workerId: 'w1' } }), lastEventId: '5' };
  sources[0].onmessage!(message); sources[0].onmessage!(message);
  expect(useMirrorStore.getState().activeWorkers).toEqual(['w1']);
  expect(useMirrorStore.getState().recentEvents).toHaveLength(1);
  expect(publishCognition).not.toHaveBeenCalled();
});
it('malformed and cursorless events leave the projection untouched', async () => {
  await startMirrorClient();
  sources[0].onmessage!({ data: '[]', lastEventId: '8' });
  sources[0].onmessage!({ data: JSON.stringify({ eventType: 'worker.started', payload: { workerId: 'w1' } }), lastEventId: '' });
  expect(useMirrorStore.getState().lastEventId).toBe(4);
  expect(useMirrorStore.getState().activeWorkers).toEqual([]);
});
it('disconnect preserves last-known entities, marks them stale, and stop cancels retries', async () => {
  vi.mocked(fetch).mockResolvedValue(response({ ...snapshot(), active_workers: ['w1'] }));
  await startMirrorClient(); sources[0].onopen!(); sources[0].onerror!();
  expect(useMirrorStore.getState()).toMatchObject({ activeWorkers: ['w1'], projection: 'stale', connection: 'connecting' });
  stopMirrorClient(); await vi.advanceTimersByTimeAsync(60000);
  expect(fetch).toHaveBeenCalledTimes(1);
});
