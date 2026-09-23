/**
 * Product-owned result language. This is a presentation contract only: it
 * never upgrades completion into verification and never decides authority.
 */
export type ReceiptKind =
  | 'verified-success'
  | 'finished-unverified'
  | 'refusal'
  | 'failure'
  | 'failure-rollback';

export type ReceiptAction =
  | 'See changes'
  | 'Why verified'
  | 'Review'
  | 'Run a check'
  | 'Discard'
  | 'Choose a safer option'
  | 'Explain'
  | 'See what failed'
  | 'Try another approach'
  | 'Undo';

export interface Receipt {
  kind: ReceiptKind;
  title: string;
  message: string;
  target: string;
  actions: ReceiptAction[];
  /** Available only when the underlying result actually supplied it. */
  targetTabId?: string;
}

export interface ReceiptInput {
  action: 'authorize' | 'reject';
  succeeded: boolean;
  target: string;
  /** Verification remains unknown until a real verifier result arrives. */
  verification: 'pass' | 'fail' | 'unknown';
  /** True only when a real restoration receipt was observed. */
  restored?: boolean;
  /** True only when the source supplied a currently valid, guarded recovery action. */
  undoAvailable?: boolean;
  targetTabId?: string;
}

export function deriveReceipt(input: ReceiptInput): Receipt {
  if (input.action === 'reject') {
    return {
      kind: 'refusal',
      title: 'I did not do that.',
      message: input.succeeded
        ? 'It would have exceeded your permission.'
        : 'The decline was not confirmed by the server. This interface did not authorize the action.',
      target: input.target,
      actions: ['Choose a safer option', 'Explain'],
      targetTabId: input.targetTabId,
    };
  }

  if (!input.succeeded) {
    return input.restored
      ? {
          kind: 'failure-rollback',
          title: 'That did not work.',
          message: 'The change failed verification. The previous state was restored.',
          target: input.target,
          actions: ['See what failed', 'Try another approach'],
          targetTabId: input.targetTabId,
        }
      : {
          kind: 'failure',
          title: 'That did not work.',
          message: 'The request did not complete. Its verification state is unknown.',
          target: input.target,
          actions: ['See what failed', 'Try another approach'],
          targetTabId: input.targetTabId,
        };
  }

  if (input.verification === 'fail') {
    return input.restored
      ? {
          kind: 'failure-rollback',
          title: 'That did not work.',
          message: 'The change failed verification. The previous state was restored.',
          target: input.target,
          actions: ['See what failed', 'Try another approach'],
          targetTabId: input.targetTabId,
        }
      : {
          kind: 'failure',
          title: 'That did not work.',
          message: 'The change failed verification. Review what failed before trying again.',
          target: input.target,
          actions: ['See what failed', 'Try another approach'],
          targetTabId: input.targetTabId,
        };
  }

  if (input.verification === 'pass') {
    const actions: ReceiptAction[] = ['See changes'];
    if (input.undoAvailable === true) actions.push('Undo');
    actions.push('Why verified');
    return {
      kind: 'verified-success',
      title: 'Done',
      message: 'The work completed and verification passed.',
      target: input.target,
      actions,
      targetTabId: input.targetTabId,
    };
  }

  return {
    kind: 'finished-unverified',
    title: 'Finished, but not verified',
    message: 'The work finished, but I could not verify it yet.',
    target: input.target,
    actions: ['Review', 'Run a check', 'Discard'],
    targetTabId: input.targetTabId,
  };
}
