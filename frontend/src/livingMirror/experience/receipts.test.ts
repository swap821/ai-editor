import { describe, expect, it } from 'vitest';
import { deriveReceipt } from './receipts';

describe('result receipts', () => {
  const base = { action: 'authorize' as const, succeeded: true, target: 'demo.py' };

  it('keeps completed work unverified until a verifier passes', () => {
    expect(deriveReceipt({ ...base, verification: 'unknown' })).toMatchObject({
      kind: 'finished-unverified',
      title: 'Finished, but not verified',
    });
  });

  it('only uses verified-success for a real pass', () => {
    expect(deriveReceipt({ ...base, verification: 'pass' })).toMatchObject({
      kind: 'verified-success',
      message: 'The work completed and verification passed.',
    });
    expect(deriveReceipt({ ...base, verification: 'fail' }).kind).toBe('failure');
  });

  it('does not invent an Undo action without measured recovery evidence', () => {
    expect(deriveReceipt({ ...base, verification: 'pass' }).actions).not.toContain('Undo');
  });

  it('offers Undo only when the source explicitly reports recovery availability', () => {
    expect(deriveReceipt({ ...base, verification: 'pass', undoAvailable: true })).toMatchObject({
      kind: 'verified-success',
      actions: ['See changes', 'Undo', 'Why verified'],
    });
  });

  it('presents refusal as a safe governance result', () => {
    expect(deriveReceipt({ ...base, action: 'reject', verification: 'unknown' })).toMatchObject({
      kind: 'refusal',
      title: 'I did not do that.',
    });
  });

  it('does not make an unconfirmed decline sound like a confirmed refusal', () => {
    expect(deriveReceipt({ ...base, action: 'reject', succeeded: false, verification: 'unknown' })).toMatchObject({
      kind: 'refusal',
      message: 'The decline was not confirmed by the server. This interface did not authorize the action.',
    });
  });

  it('does not claim restoration unless it is measured', () => {
    expect(deriveReceipt({ ...base, succeeded: false, verification: 'fail' }).kind).toBe('failure');
    expect(deriveReceipt({ ...base, succeeded: false, verification: 'fail', restored: true }).kind).toBe('failure-rollback');
  });
});
