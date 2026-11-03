import { describe, expect, it } from 'vitest';
import { canonicalPayload } from './eventPayload';

describe('canonicalPayload', () => {
  it('prefers an explicit payload and returns a copy without mutating inputs', () => {
    const payload = { kind: 'tick' };
    const envelope = { missionId: 'm1', payload: { kind: 'ignored' } };
    const result = canonicalPayload(envelope, payload);
    expect(result).toEqual({ kind: 'tick', missionId: 'm1' });
    expect(payload).toEqual({ kind: 'tick' });
    expect(result).not.toBe(payload);
  });

  it('uses envelope.payload when it is a record, otherwise the envelope itself', () => {
    expect(canonicalPayload({ payload: { a: 1 }, turnId: 't1' })).toEqual({ a: 1, turnId: 't1' });
    expect(canonicalPayload({ payload: 'not-a-record', b: 2 })).toEqual({ payload: 'not-a-record', b: 2 });
  });

  it('lifts snake_case or camelCase envelope identity into camelCase payload keys', () => {
    const result = canonicalPayload(
      { mission_id: 'm1', workerId: 'w1', turn_id: 't1' },
      { text: 'hi' },
    );
    expect(result).toEqual({ text: 'hi', missionId: 'm1', workerId: 'w1', turnId: 't1' });
  });

  it('accepts historical nested IDs that agree with the envelope', () => {
    const result = canonicalPayload(
      { missionId: 'm1', worker_id: 'w1' },
      { mission_id: 'm1', workerId: 'w1' },
    );
    expect(result.missionId).toBe('m1');
    expect(result.workerId).toBe('w1');
    expect(result.mission_id).toBe('m1');
  });

  it('throws when a nested ID conflicts with the envelope ID', () => {
    expect(() => canonicalPayload({ missionId: 'm1' }, { missionId: 'm2' }))
      .toThrow('Conflicting missionId in canonical event');
    expect(() => canonicalPayload({ worker_id: 'w1' }, { worker_id: 'w2' }))
      .toThrow('Conflicting workerId in canonical event');
  });

  it('ignores empty or non-string envelope IDs and leaves nested ones alone', () => {
    const result = canonicalPayload({ missionId: '', turnId: 5 }, { missionId: 'nested', turnId: 'x' });
    expect(result).toEqual({ missionId: 'nested', turnId: 'x' });
  });
});
