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
});
