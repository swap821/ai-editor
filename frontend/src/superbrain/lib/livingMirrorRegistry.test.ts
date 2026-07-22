import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  dispatchLivingMirrorEvent,
  registeredMirrorEventTypes,
} from './livingMirrorRegistry';
import { useMirrorStore } from './mirrorStore';
import { publishCognition } from './cognitionBus';

vi.mock('./cognitionBus', () => ({
  publishCognition: vi.fn(),
}));

vi.mock('./aiosAdapter', () => ({
  humanizeRedactionMarkers: (value: string) => value,
}));

vi.mock('./swarmHUDStore', () => ({
  endSwarmCaste: vi.fn(),
  markSwarmCloudSubtask: vi.fn(),
  startSwarmCaste: vi.fn(),
  startSwarmPlan: vi.fn(),
}));

const resetMirror = () => {
  useMirrorStore.setState({
    status: 'offline',
    pendingEvents: 0,
    phase: 'idle',
    activeCastes: [],
    activeMissions: [],
    activeWorkers: [],
    activeModels: [],
    approvalRequired: false,
    lastVerification: null,
    lastAnnouncement: null,
    snapshotRequired: false,
    recentEvents: [],
    lastEventId: null,
    bootFacts: null,
  });
};

const event = (id: number, eventType: string, payload: Record<string, unknown>, schemaVersion: string = '1') => ({
  id,
  eventType,
  canonical: { eventId: `event-${id}`, eventType, schema_version: schemaVersion, payload, ...payload },
  payload,
});

describe('Living Mirror reaction registry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetMirror();
  });

  it('ignores unknown event families without mutating the read model', () => {
    expect(dispatchLivingMirrorEvent(event(1, 'future.authority_event', { status: 'running' }))).toBe(false);
    expect(useMirrorStore.getState().lastEventId).toBeNull();
    expect(useMirrorStore.getState().recentEvents).toHaveLength(0);
    expect(publishCognition).not.toHaveBeenCalled();
  });

  it('rejects malformed known events before read-model mutation or reaction', () => {
    expect(dispatchLivingMirrorEvent(event(2, 'worker.started', {}))).toBe(true);
    expect(useMirrorStore.getState().lastEventId).toBeNull();
    expect(useMirrorStore.getState().recentEvents).toHaveLength(0);
    expect(useMirrorStore.getState().lastAnnouncement).toBe('Incomplete backend event ignored.');
    expect(publishCognition).not.toHaveBeenCalled();
  });

  it('accepts canonical snake-case worker fields and dissolves the worker', () => {
    dispatchLivingMirrorEvent(event(3, 'worker.started', { worker_id: 'worker-1', role: 'tester' }));
    expect(useMirrorStore.getState().activeWorkers).toEqual(['worker-1']);
    expect(useMirrorStore.getState().activeCastes).toEqual(['tester']);
    expect(publishCognition).toHaveBeenCalled();

    dispatchLivingMirrorEvent(event(4, 'worker.dissolved', { worker_id: 'worker-1', role: 'tester' }));
    expect(useMirrorStore.getState().activeWorkers).toEqual([]);
    expect(useMirrorStore.getState().activeCastes).toEqual([]);
  });

  it('applies worker identity and caste from the canonical nested payload', () => {
    useMirrorStore.getState().applyEvent(7, 'worker.started', {
      eventId: 'event-7',
      eventType: 'worker.started',
      payload: { worker_id: 'worker-nested', role: 'reviewer' },
    });
    expect(useMirrorStore.getState().activeWorkers).toEqual(['worker-nested']);
    expect(useMirrorStore.getState().activeCastes).toEqual(['reviewer']);

    useMirrorStore.getState().applyEvent(8, 'worker.dissolved', {
      eventId: 'event-8',
      eventType: 'worker.dissolved',
      payload: { worker_id: 'worker-nested', role: 'reviewer' },
    });
    expect(useMirrorStore.getState().activeWorkers).toEqual([]);
    expect(useMirrorStore.getState().activeCastes).toEqual([]);
  });

  it('marks the portrait stale when replay requires a fresh snapshot', () => {
    dispatchLivingMirrorEvent(event(5, 'snapshot_required', {}));
    expect(useMirrorStore.getState().status).toBe('stale');
    expect(useMirrorStore.getState().snapshotRequired).toBe(true);
    expect(useMirrorStore.getState().lastAnnouncement).toContain('fresh snapshot');
  });

  it('records verification observations and exposes only registered reactions', () => {
    dispatchLivingMirrorEvent(event(6, 'verification.passed', { target: 'tests', strength: 'strong' }));
    expect(useMirrorStore.getState().lastVerification).toMatchObject({
      eventType: 'verification.passed',
      payload: { target: 'tests', strength: 'strong' },
    });
    expect(registeredMirrorEventTypes()).toContain('verification.passed');
    expect(registeredMirrorEventTypes()).not.toContain('authority.grant');
  });

  it('registers the real worker-lifecycle canonical events found on the backend', () => {
    const registered = registeredMirrorEventTypes();
    for (const eventType of [
      'worker.requested',
      'worker.admitted',
      'worker.awaiting_capability',
      'worker.failed',
      'worker.killed',
      'facts.proposed',
      'route.selected',
    ]) {
      expect(registered).toContain(eventType);
    }
  });

  it('removes a failed worker from the active set -- previously impossible because the event was dropped before mirrorStore.applyEvent ever ran', () => {
    dispatchLivingMirrorEvent(event(10, 'worker.started', { worker_id: 'worker-x', role: 'coder' }));
    expect(useMirrorStore.getState().activeWorkers).toEqual(['worker-x']);

    dispatchLivingMirrorEvent(event(11, 'worker.failed', { worker_id: 'worker-x', reason: 'timeout' }));

    expect(useMirrorStore.getState().activeWorkers).toEqual([]);
    expect(publishCognition).toHaveBeenCalled();
  });

  it('removes a killed worker from the active set the same way', () => {
    dispatchLivingMirrorEvent(event(12, 'worker.started', { worker_id: 'worker-y', role: 'reviewer' }));
    dispatchLivingMirrorEvent(event(13, 'worker.killed', { worker_id: 'worker-y', reason: 'scheduler cancellation' }));

    expect(useMirrorStore.getState().activeWorkers).toEqual([]);
  });

  it('dispatches worker.requested and worker.admitted without touching the active worker set yet', () => {
    expect(dispatchLivingMirrorEvent(event(14, 'worker.requested', { worker_id: 'worker-z' }))).toBe(true);
    expect(dispatchLivingMirrorEvent(event(15, 'worker.admitted', { worker_id: 'worker-z', strategy: 'deterministic' }))).toBe(true);
    expect(useMirrorStore.getState().activeWorkers).toEqual([]);
    expect(publishCognition).toHaveBeenCalledTimes(2);
  });

  it('dispatches worker.awaiting_capability as an approval-required reaction', () => {
    expect(
      dispatchLivingMirrorEvent(
        event(16, 'worker.awaiting_capability', { worker_id: 'worker-w', reason: 'needs filesystem write' }),
      ),
    ).toBe(true);
    expect(publishCognition).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'approval-required' }),
    );
  });

  it('dispatches facts.proposed and route.selected from their real backend payload shapes', () => {
    expect(dispatchLivingMirrorEvent(event(17, 'facts.proposed', { count: 3 }))).toBe(true);
    expect(useMirrorStore.getState().lastAnnouncement).toBe('3 facts proposed for memory.');

    expect(
      dispatchLivingMirrorEvent(
        event(18, 'route.selected', { provider: 'ollama', model: 'granite3.2:2b', privacy: 'local' }),
      ),
    ).toBe(true);
    expect(publishCognition).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'route', detail: 'ollama:granite3.2:2b (local)' }),
    );
  });
});
