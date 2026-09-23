import { describe, expect, it } from 'vitest';
import { presentHistoryEvent, type HistoryEvent } from './historyPresentation';

const event: HistoryEvent = {
  id: 7,
  type: 'worker.started',
  summary: 'Worker started: worker-secret-42',
  occurredAt: '2026-09-22T12:00:00.000Z',
  receivedAt: '2026-09-22T12:00:01.000Z',
  missionId: 'mission-secret-42',
  workerId: 'worker-secret-42',
};

describe('history presentation', () => {
  it('redacts internal vocabulary and identities in Guided mode', () => {
    const presented = presentHistoryEvent(event, 'guided');

    expect(presented).toMatchObject({
      label: 'Temporary work updated',
      message: 'Temporary work is being coordinated.',
      occurredAt: event.occurredAt,
      receivedAt: event.receivedAt,
    });
    expect(JSON.stringify(presented)).not.toContain('worker.started');
    expect(JSON.stringify(presented)).not.toContain('mission-secret-42');
    expect(JSON.stringify(presented)).not.toContain('worker-secret-42');
    expect(JSON.stringify(presented)).not.toContain('Worker started');
  });

  it('preserves diagnostic event details in Expert mode', () => {
    expect(presentHistoryEvent(event, 'expert')).toMatchObject({
      label: 'worker.started',
      message: event.summary,
      technical: {
        type: event.type,
        summary: event.summary,
        missionId: event.missionId,
        workerId: event.workerId,
      },
    });
  });

  it('uses measured human labels for safety and verification events', () => {
    expect(presentHistoryEvent({ ...event, type: 'security.refusal.recorded' }, 'guided')).toMatchObject({
      label: 'Action declined safely',
      message: 'GAGOS stopped at the permission boundary.',
    });
    expect(presentHistoryEvent({ ...event, type: 'verify_result' }, 'guided')).toMatchObject({
      label: 'Result check recorded',
      message: 'A result check was recorded.',
    });
  });

  it('humanizes the live approval aliases emitted by the mirror', () => {
    expect(presentHistoryEvent({ ...event, type: 'human_required' }, 'guided')).toMatchObject({
      label: 'Permission needed',
      message: 'GAGOS is waiting for your permission before it continues.',
    });
    expect(presentHistoryEvent({ ...event, type: 'approval.decided' }, 'guided')).toMatchObject({
      label: 'Permission recorded',
      message: 'Your permission decision was recorded.',
    });
  });
});
