import { beforeEach, expect, it } from 'vitest';
import { useMirrorStore } from './mirrorStore';

beforeEach(() => useMirrorStore.setState(useMirrorStore.getInitialState(), true));
const emit = (id: number, type: string, payload: Record<string, unknown>) => useMirrorStore.getState().applyEvent(id, type, { payload });

it('keeps two approvals independent and ignores unbound resolutions', () => {
  emit(1, 'approval.required', { missionId: 'm1', requestId: 'r1' });
  emit(2, 'approval.required', { missionId: 'm2', requestId: 'r2' });
  emit(3, 'approval.resolved', { missionId: 'm1', requestId: 'r1', decision: 'approve' });
  expect(useMirrorStore.getState().approvalRequired).toBe(true);
  emit(4, 'approval.resolved', {});
  expect(useMirrorStore.getState().approvalRequired).toBe(true);
});

it('one worker dissolving does not remove a role still held by another worker', () => {
  emit(1, 'worker.started', { workerId: 'w1', missionId: 'm1', role: 'coder' });
  emit(2, 'worker.started', { workerId: 'w2', missionId: 'm2', role: 'coder' });
  emit(3, 'worker.dissolved', { workerId: 'w1', role: 'coder' });
  expect(useMirrorStore.getState().activeCastes).toContain('coder');
  expect(useMirrorStore.getState().activeWorkers).toEqual(['w2']);
});

it('one completion leaves another mission running and verification bound to its mission', () => {
  emit(1, 'mission.running', { missionId: 'm1' });
  emit(2, 'mission.running', { missionId: 'm2' });
  emit(3, 'mission.completed', { missionId: 'm1' });
  emit(4, 'turn.completed', { missionId: 'm1' });
  expect(useMirrorStore.getState().phase).not.toBe('idle');
  emit(5, 'verify_result', { missionId: 'm1', verdict: 'pass', target: 'a.py' });
  emit(6, 'verify_result', { missionId: 'm2', verdict: 'fail', target: 'b.py' });
  const state = useMirrorStore.getState();
  expect(Object.values(state.verifications).map((v) => v.missionId)).toEqual(['m1', 'm2']);
  expect(state.activeMissions).toEqual(['m2']);
});

it('missing observation time remains unknown rather than being replaced by receipt time', () => {
  emit(1, 'worker.started', { workerId: 'w1' });
  expect(useMirrorStore.getState().recentEvents[0].occurredAt).toBeNull();
  expect(useMirrorStore.getState().recentEvents[0].receivedAt).toEqual(expect.any(String));
});

it('stream connection and a partial snapshot cannot establish fresh complete operational state', () => {
  useMirrorStore.getState().setConnection('connected');
  expect(useMirrorStore.getState().projection).toBe('unknown');
  useMirrorStore.getState().setSnapshot({ status: 'online', active_workers: ['w1'], last_event_id: 4 });
  expect(useMirrorStore.getState().projection).not.toBe('fresh');
  expect(useMirrorStore.getState().observations.activeMissions.status).toBe('unavailable');
  useMirrorStore.getState().setSnapshot({ status: 'online', active_missions: [], last_event_id: 5 });
  expect(useMirrorStore.getState().observations.activeWorkers.status).toBe('stale');
  expect(useMirrorStore.getState().activeWorkers).toEqual(['w1']);
});
