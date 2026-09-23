'use client';

/**
 * Product-owned Guided approval surface.
 *
 * The adapter callbacks are intentionally the same audited paths used by the
 * technical approval panel. This component changes only the explanation and
 * presentation of the human boundary; it does not decide authority.
 */

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import {
  approvePendingApproval,
  rejectPendingApproval,
  type PendingApproval,
} from '@/lib/aiosAdapter';
import { recordFrontendMetric } from './observability/frontendMetrics';
import { measuredLatency } from './observability/latency';

function monotonicNow(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : 0;
}

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
    // Keep the backend-provided value when it is not a parseable URL.
  }
  return (
    <div className="approval-browse" aria-label="Public web page request">
      <div className="approval-browse-domain">{domain}</div>
      <div className="approval-browse-url">{url}</div>
      {explanation ? <p className="approval-browse-note">{explanation}</p> : null}
      <p className="approval-browse-shield">
        This sends the page content to GAGOS so it can answer. The approval
        record names this public page; it does not include local files or
        credentials.
      </p>
    </div>
  );
}

export interface GuidedApprovalOutcome {
  action: 'authorize' | 'reject';
  kind: PendingApproval['kind'];
  filepath: string;
  content: string;
  diff: string;
  succeeded: boolean;
  /** The replay reached another real approval boundary before completing. */
  paused: boolean;
}

function actionLabel(pending: PendingApproval): string {
  switch (pending.kind) {
    case 'create': return pending.filepath ? `create ${pending.filepath}` : 'create a project file';
    case 'edit': return pending.filepath ? `change ${pending.filepath}` : 'change a project file';
    case 'command': return 'run a command in the project';
    case 'browse': return pending.url ? 'fetch a web page' : 'fetch the requested page';
    default: return pending.summary || 'perform the requested action';
  }
}

function impactLabel(pending: PendingApproval): string {
  switch (pending.kind) {
    case 'create':
    case 'edit':
      return pending.filepath
        ? `The approval names ${pending.filepath}. A complete effect boundary is not included in the approval record.`
        : 'The approval record does not include a complete effect boundary.';
    case 'command':
      return pending.command
        ? 'The approval names the command shown in Explain. A complete effect boundary is not included in the approval record.'
        : 'The approval record does not include a complete effect boundary.';
    case 'browse': return 'The requested page content may be sent to GAGOS to answer this request.';
    default: return pending.explanation || 'The effect is not fully described by the available evidence.';
  }
}

export function GuidedApprovalPanel({
  pending,
  onSettled,
}: {
  pending: PendingApproval;
  onSettled: (outcome?: GuidedApprovalOutcome) => void;
}) {
  const [busy, setBusy] = useState<'authorize' | 'reject' | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const firstActionRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const renderStartedAtRef = useRef(monotonicNow());

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    firstActionRef.current?.focus();
    return () => {
      const previous = previousFocusRef.current;
      if (previous?.isConnected) previous.focus();
    };
  }, [pending.token]);

  useEffect(() => {
    recordFrontendMetric('approval-render', measuredLatency(renderStartedAtRef.current, monotonicNow()));
    renderStartedAtRef.current = monotonicNow();
  }, [pending.token]);

  // This is a real modal boundary, not just a visually prominent card. Keep
  // keyboard focus inside it while the server-issued decision is pending;
  // authority remains entirely in the audited callbacks below.
  const trapFocus = useCallback((event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Tab') return;
    const panel = panelRef.current;
    if (!panel) return;
    const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
      'button:not([disabled]), summary, a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])',
    )).filter((element) => element.getAttribute('aria-hidden') !== 'true');
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !panel.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }, []);

  const authorize = useCallback(() => {
    setBusy('authorize');
    void (async () => {
      let succeeded = false;
      let paused = false;
      try {
        const result = await approvePendingApproval();
        paused = result.paused;
        // `ok` also covers a legitimate human_required pause. That is not a
        // completed result: the next server-issued boundary must remain the
        // visible state until it is resolved.
        succeeded = result.ok && !result.paused;
      } catch {
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
          paused,
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
          paused: false,
        });
      }
    })();
  }, [onSettled, pending.kind, pending.filepath, pending.content, pending.diff]);

  return (
    <section
      ref={panelRef}
      className="approval-panel approval-panel--guided"
      role="alertdialog"
      aria-modal="true"
      aria-label="GAGOS permission request"
      aria-describedby="guided-approval-summary guided-approval-impact guided-approval-denial"
      onKeyDown={trapFocus}
    >
      <header className="approval-head">
        <span className="approval-title">GAGOS wants your permission</span>
        <span id="guided-approval-summary" className="approval-summary">
          It wants to {actionLabel(pending)}.
        </span>
      </header>

      <dl className="approval-human-facts" aria-label="Permission details">
        <div><dt>What</dt><dd>{actionLabel(pending)}</dd></div>
        <div><dt>Where</dt><dd>{pending.filepath || pending.url || 'No specific location is included in this approval record.'}</dd></div>
        <div id="guided-approval-impact"><dt>It can affect</dt><dd>{impactLabel(pending)}</dd></div>
        <div id="guided-approval-denial"><dt>If you say no</dt><dd>GAGOS will not perform this action.</dd></div>
      </dl>

      <details className="approval-evidence">
        <summary>Explain</summary>
        {pending.summary ? <p className="approval-explanation">{pending.summary}</p> : null}
        {pending.explanation ? <p className="approval-explanation">{pending.explanation}</p> : null}
        {pending.kind === 'browse' && pending.url ? (
          <BrowseView url={pending.url} explanation={pending.explanation} />
        ) : pending.diff ? (
          <DiffView diff={pending.diff} />
        ) : pending.command ? (
          <pre className="approval-diff approval-command">{pending.command}</pre>
        ) : null}
      </details>

      <div className="approval-actions">
        <button
          type="button"
          className="approval-authorize"
          ref={firstActionRef}
          onClick={authorize}
          disabled={busy !== null}
        >
          {busy === 'authorize' ? 'Allowing…' : 'Allow once'}
        </button>
        <button
          type="button"
          className="approval-reject"
          onClick={reject}
          disabled={busy !== null}
        >
          {busy === 'reject' ? 'Declining…' : "Don't allow"}
        </button>
      </div>
      <i className="glass-grain" aria-hidden />
    </section>
  );
}

export default GuidedApprovalPanel;
