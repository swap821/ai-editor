import { beforeEach, describe, expect, it } from 'vitest';
import { useMirrorStore } from './mirrorStore';

/** Phase-3-style resync invariant (found while reviewing the frontend audit):
 *  "A resynchronization replaces authoritative collections; it does not
 *  preserve stale entities accidentally." setSnapshot() is the one function
 *  a fresh/replay-gap snapshot goes through (aiosMirror.ts's
 *  refreshMirrorSnapshot()), so this locks in that a stale worker/mission/
 *  caste from before a resync is actually dropped, not left lying around
 *  because the new snapshot no longer mentions it. */
describe('mirrorStore setSnapshot resync behavior', () => {
  beforeEach(() => {
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
      lastTurnStartedEventId: null,
      lastVerificationEventId: null,
      turnAttributionInvalidated: false,
      bootFacts: null,
    });
  });

  it('replaces the active-worker set on resync rather than merging with stale entries', () => {
    useMirrorStore.getState().setSnapshot({
      status: 'online',
      active_workers: ['worker-old-1', 'worker-old-2'],
      active_castes: ['coder'],
      active_missions: ['mission-old'],
    });
    expect(useMirrorStore.getState().activeWorkers).toEqual(['worker-old-1', 'worker-old-2']);

    // A resync (e.g. after snapshot_required) reports a completely different
    // set -- none of the old entries survived on the backend.
    useMirrorStore.getState().setSnapshot({
      status: 'online',
      active_workers: ['worker-new-1'],
      active_castes: ['reviewer'],
      active_missions: [],
    });

    const state = useMirrorStore.getState();
    expect(state.activeWorkers).toEqual(['worker-new-1']);
    expect(state.activeWorkers).not.toContain('worker-old-1');
    expect(state.activeWorkers).not.toContain('worker-old-2');
    expect(state.activeCastes).toEqual(['reviewer']);
    expect(state.activeCastes).not.toContain('coder');
    // An empty array is real, measured emptiness -- must replace, not be
    // mistaken for "no data" and fall back to the stale value.
    expect(state.activeMissions).toEqual([]);
  });

  it('drops pre-snapshot worker event details so replay cannot rematerialize old motes', () => {
    useMirrorStore.getState().applyEvent(4, 'worker.completed', { payload: { workerId: 'worker-old' } });
    expect(useMirrorStore.getState().workers['worker-old']?.state).toBe('completed');

    useMirrorStore.getState().setSnapshot({
      status: 'online',
      state: 'measured',
      last_event_id: 4,
      active_workers: [],
    });

    expect(useMirrorStore.getState().workers).toEqual({});
  });

  it('keeps the prior state for a field the snapshot omits entirely, rather than wiping it', () => {
    useMirrorStore.getState().setSnapshot({
      status: 'online',
      active_workers: ['worker-1'],
      active_missions: ['mission-1'],
    });

    // A malformed/partial response (e.g. active_castes missing from the
    // payload) must not be treated as "castes are now empty" -- only an
    // actual array in the response is authoritative.
    useMirrorStore.getState().setSnapshot({
      status: 'online',
      active_workers: ['worker-2'],
    });

    const state = useMirrorStore.getState();
    expect(state.activeWorkers).toEqual(['worker-2']);
    expect(state.activeMissions).toEqual(['mission-1']);
  });

  it('retains turn and verifier event cursors after the bounded event history rolls over', () => {
    const store = useMirrorStore.getState();
    expect(store.applyEvent(10, 'turn.started', {})).toBe(true);
    expect(useMirrorStore.getState().applyEvent(11, 'verification.passed', { verdict: 'pass' })).toBe(true);
    for (let id = 12; id <= 311; id += 1) {
      expect(useMirrorStore.getState().applyEvent(id, 'observation.recorded', {})).toBe(true);
    }

    const state = useMirrorStore.getState();
    expect(state.recentEvents).toHaveLength(256);
    expect(state.recentEvents[0].id).toBe(56);
    expect(state.lastTurnStartedEventId).toBe(10);
    expect(state.lastVerificationEventId).toBe(11);
  });

  it('keeps turn attribution invalid after a required snapshot until a new turn boundary arrives', () => {
    const store = useMirrorStore.getState();
    store.applyEvent(1, 'turn.started', {});
    useMirrorStore.getState().applyEvent(2, 'verification.passed', { verdict: 'pass' });
    useMirrorStore.getState().applyEvent(3, 'turn.completed', {});
    useMirrorStore.getState().setSnapshotRequired('replay_gap');
    useMirrorStore.getState().setSnapshot({ status: 'online', state: 'measured', snapshot_required: false, last_event_id: 9, phase: 'idle' });

    expect(useMirrorStore.getState()).toMatchObject({
      turnAttributionInvalidated: true,
      lastTurnStartedEventId: 1,
      lastVerificationEventId: 2,
    });
    useMirrorStore.getState().applyEvent(10, 'verification.passed', { verdict: 'pass' });
    expect(useMirrorStore.getState().turnAttributionInvalidated).toBe(true);
    useMirrorStore.getState().applyEvent(11, 'turn.started', {});
    expect(useMirrorStore.getState().turnAttributionInvalidated).toBe(false);
  });
});
