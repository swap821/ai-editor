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

function BrowseView({ url, explanation }: { url: string; explanation: string }) {
  let domain = url;
  try {
    domain = new URL(url).hostname;
  } catch {
    // leave raw url
  }
  return (
    <div className="approval-browse" aria-label="Public web page request">
      <div className="approval-browse-domain">{domain}</div>
      <div className="approval-browse-url">{url}</div>
      {explanation ? <p className="approval-browse-note">{explanation}</p> : null}
      <p className="approval-browse-shield">
        This sends the page content to the model. No local files or credentials
        are exposed.
      </p>
    </div>
  );
}

/** What the operator decided — passed to onSettled so a consumer (e.g. the chat
 *  chrome) can narrate the outcome in plain language. */
export interface ApprovalOutcome {
  action: 'authorize' | 'reject';
  kind: PendingApproval['kind'];
  filepath: string;
  /** The proposed artifact, so a consumer can fill a "writing" slab on authorize:
   *  full file content for a create, the unified diff for an edit. */
  content: string;
  diff: string;
  /** Whether the decision's real effect is verified, not merely requested.
   *  For 'authorize': whether the replay actually completed (the adapter's
   *  own `DirectiveResult.ok`) -- a rejected/thrown promise or a resolved
   *  `ok: false` are both real failures and must both narrate as failure,
   *  never as success. For 'reject': whether the server confirmed the
   *  decline; declining is always locally safe (nothing gets authorized
   *  either way), so `false` here means "unconfirmed by the server", not
   *  "the reject failed". */
  succeeded: boolean;
}

export default function ApprovalPanel({
  pending,
  onSettled,
}: {
  pending: PendingApproval;
  /** Called after AUTHORIZE/REJECT completes (the replay may pause again —
   *  the HUD re-reads the adapter's pending state). The outcome is optional so
   *  callers that only need to refresh (e.g. SuperbrainHUD) can ignore it. */
  onSettled: (outcome?: ApprovalOutcome) => void;
}) {
  const [busy, setBusy] = useState<'authorize' | 'reject' | null>(null);

  const authorize = useCallback(() => {
    setBusy('authorize');
    void (async () => {
      let succeeded = false;
      try {
        const result = await approvePendingApproval();
        succeeded = result.ok;
      } catch {
        // A thrown promise (e.g. the operator aborted mid-replay) is still a
        // real failure to authorize -- never treated as success.
        succeeded = false;
      } finally {
        setBusy(null);
        onSettled({
          action: 'authorize',
          kind: pending.kind,
          filepath: pending.filepath,
          content: pending.content,
          diff: pending.diff,
          succeeded,
        });
      }
    })();
  }, [onSettled, pending.kind, pending.filepath, pending.content, pending.diff]);

  const reject = useCallback(() => {
    setBusy('reject');
    void (async () => {
      let succeeded = false;
      try {
        const result = await rejectPendingApproval();
        succeeded = result.confirmed;
      } catch {
        succeeded = false;
      } finally {
        setBusy(null);
        onSettled({
          action: 'reject',
          kind: pending.kind,
          filepath: pending.filepath,
          content: pending.content,
          diff: pending.diff,
          succeeded,
        });
      }
    })();
  }, [onSettled, pending.kind, pending.filepath, pending.content, pending.diff]);

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

      {pending.kind === 'browse' && pending.url ? (
        <BrowseView url={pending.url} explanation={pending.explanation} />
      ) : pending.diff ? (
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
