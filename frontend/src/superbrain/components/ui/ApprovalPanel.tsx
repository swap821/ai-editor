'use client';

/**
 * ApprovalPanel — the operator's decision surface, inside the experience.
 *
 * When the supervised mind pauses (the amber hold), this panel presents the
 * REAL ask: the plain-language summary, the unified diff (the decision IS
 * the diff), or the exact command. AUTHORIZE redeems the server-issued
 * capability by replaying the turn; REJECT records the refusal through the
 * audited endpoint. No prose can approve anything — only these two buttons.
 */

import { useCallback, useState } from 'react';
import {
  approvePendingApproval,
  rejectPendingApproval,
  type PendingApproval,
} from '@/lib/aiosAdapter';

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="approval-diff" aria-label="Proposed change">
      {diff.split('\n').map((line, index) => {
        const kind = line.startsWith('+++') || line.startsWith('---')
          ? 'diff-file'
          : line.startsWith('@@')
            ? 'diff-hunk'
            : line.startsWith('+')
              ? 'diff-add'
              : line.startsWith('-')
                ? 'diff-del'
                : '';
        return (
          <span key={index} className={kind}>
            {line}
            {'\n'}
          </span>
        );
      })}
    </pre>
  );
}

export default function ApprovalPanel({
  pending,
  onSettled,
}: {
  pending: PendingApproval;
  /** Called after AUTHORIZE/REJECT completes (the replay may pause again —
   *  the HUD re-reads the adapter's pending state). */
  onSettled: () => void;
}) {
  const [busy, setBusy] = useState<'authorize' | 'reject' | null>(null);

  const authorize = useCallback(() => {
    setBusy('authorize');
    void approvePendingApproval().finally(() => {
      setBusy(null);
      onSettled();
    });
  }, [onSettled]);

  const reject = useCallback(() => {
    setBusy('reject');
    void rejectPendingApproval().finally(() => {
      setBusy(null);
      onSettled();
    });
  }, [onSettled]);

  return (
    <section className="approval-panel" role="alertdialog" aria-label="Operator approval required">
      <header className="approval-head">
        <span className="approval-title">
          OPERATOR APPROVAL REQUIRED
          {/* The backend names the exact action — the title says precisely
              what is being authorized, never a vague ask. */}
          {pending.kind !== 'other' ? ` · ${pending.kind.toUpperCase()}` : ''}
          {pending.filepath ? ` · ${pending.filepath}` : ''}
        </span>
        <span className="approval-summary">{pending.summary}</span>
      </header>

      {pending.explanation ? (
        <p className="approval-explanation">{pending.explanation}</p>
      ) : null}

      {pending.diff ? (
        <DiffView diff={pending.diff} />
      ) : pending.command ? (
        <pre className="approval-diff approval-command">{pending.command}</pre>
      ) : null}

      <div className="approval-actions">
        <button
          type="button"
          className="approval-authorize"
          onClick={authorize}
          disabled={busy !== null}
        >
          {busy === 'authorize' ? 'EXECUTING…' : 'AUTHORIZE'}
        </button>
        <button
          type="button"
          className="approval-reject"
          onClick={reject}
          disabled={busy !== null}
        >
          {busy === 'reject' ? 'STANDING DOWN…' : 'REJECT'}
        </button>
      </div>
      <i className="glass-grain" aria-hidden />
    </section>
  );
}
