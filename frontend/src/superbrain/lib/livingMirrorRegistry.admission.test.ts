import { beforeEach, expect, it, vi } from 'vitest';
import { useMirrorStore } from './mirrorStore';
import { dispatchLivingMirrorEvent } from './livingMirrorRegistry';
import { publishCognition } from './cognitionBus';
vi.mock('./cognitionBus', () => ({ publishCognition: vi.fn() }));
vi.mock('./aiosAdapter', () => ({ humanizeRedactionMarkers: (s: string) => s }));
beforeEach(() => { useMirrorStore.setState(useMirrorStore.getInitialState(), true); vi.clearAllMocks(); });
const event = (id: number, replay = false) => ({ id, replay, eventType: 'worker.started', canonical: { schemaVersion: '1' }, payload: { workerId: 'w1', missionId: 'm1', role: 'coder' } });

it('duplicate events produce exactly one operational reaction and one history record', () => {
  dispatchLivingMirrorEvent(event(5));
  const announcement = useMirrorStore.getState().lastAnnouncement;
  dispatchLivingMirrorEvent(event(5));
  dispatchLivingMirrorEvent(event(4));
  expect(publishCognition).toHaveBeenCalledTimes(1);
  expect(useMirrorStore.getState().recentEvents).toHaveLength(1);
  expect(useMirrorStore.getState().lastAnnouncement).toBe(announcement);
});
it('replay updates entity observations silently, including gaps in a filtered cursor sequence', () => {
  dispatchLivingMirrorEvent(event(5, true));
  dispatchLivingMirrorEvent(event(25, true));
  expect(useMirrorStore.getState().activeWorkers).toEqual(['w1']);
  expect(useMirrorStore.getState().lastEventId).toBe(25);
  expect(useMirrorStore.getState().lastAnnouncement).toBeNull();
  expect(publishCognition).not.toHaveBeenCalled();
});
it('unsupported schemas neither mutate entities nor animate', () => {
  dispatchLivingMirrorEvent({ ...event(1), canonical: { schemaVersion: '99' } });
  expect(useMirrorStore.getState().lastEventId).toBeNull();
  expect(useMirrorStore.getState().compatibility).toContain('99');
  expect(publishCognition).not.toHaveBeenCalled();
});
it('capability secrets are excluded from entity projections and reactions', () => {
  dispatchLivingMirrorEvent({ ...event(1), payload: { ...event(1).payload, approvalToken: 'must-not-escape', nested: { authorization: 'also-private' } } });
  expect(JSON.stringify(useMirrorStore.getState().workers)).not.toContain('must-not-escape');
  expect(JSON.stringify(vi.mocked(publishCognition).mock.calls)).not.toContain('also-private');
});

it('admits the actual CanonicalEvent.to_dict envelope identities from the worker spawner', () => {
  const canonical = { schemaVersion: '1.0', eventId: 'event-real', eventType: 'worker.started', phase: 'execution', status: 'running', trust: 'measured',
    source: 'spawner', sessionId: 'session-1', missionId: 'm1', workerId: 'w1', turnId: null, occurredAt: '2026-09-15T03:00:00Z', payload: { role: 'coder' }, evidenceRefs: [] };
  dispatchLivingMirrorEvent({ id: 1, eventType: 'worker.started', canonical, payload: canonical.payload });
  expect(useMirrorStore.getState().workers.w1).toMatchObject({ missionId: 'm1', role: 'coder' });
  dispatchLivingMirrorEvent({ id: 2, eventType: 'worker.completed', canonical: { ...canonical, eventType: 'worker.completed' }, payload: canonical.payload });
  expect(useMirrorStore.getState().activeWorkers).toEqual([]);
});
