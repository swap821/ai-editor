import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  getPendingApproval,
  approvePendingApproval,
  rejectPendingApproval,
} from '../../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';
import './approval-safety-net.css';

/* ─── APPROVAL SAFETY-NET ("PENDING APPROVAL RESOLVER") ──────────────────────────
   A product-side, additive fallback for the canon <ApprovalPanel>. The canon panel
   (frozen #hud-portal-root) is gated on the HUD's LOCAL pendingApproval state, set
   only from the mount seed and the transient 'approval-required' bus event. If that
   event is missed (HUD remount race, GPU-loss recovery, slow Suspense) the canon
   panel never renders and the run hangs with no actionable control — even though the
   adapter's pendingApproval + the server token persist and stay valid.

   This guard owns its OWN truth, derived ONLY from the persisted adapter source
   (getPendingApproval()), reconciled from THREE redundant sources (poll + bus +
   visibility/focus) so the surface CANNOT be "missed". It is deferred behind a grace
   window so it appears ONLY when the canon panel demonstrably failed to within 1.5s
   — never a second panel in the healthy path (zero double UI, zero behavior change).

   It self-portals into document.body (NOT the frozen #hud-portal-root the canon HUD
   owns) so the shell's stacking context is irrelevant and it can NEVER enter the R3F
   reconciler or perturb the brain's voyage. Pointer-transparent wrapper at z-index
   62 — the NEW CEILING: ABOVE the canon command-bar/approval/dock band (z 60,
   shell.css) and the OrgansDock (z 55, organs.css), so its AUTHORIZE/REJECT buttons
   are always clickable; the transparent wrapper never steals clicks elsewhere.

   Uses ONLY the exported adapter API (getPendingApproval / approvePendingApproval /
   rejectPendingApproval). It never reaches into the frozen HUD or ApprovalPanel.
   ──────────────────────────────────────────────────────────────────────────── */

const POLL_MS = 1200; // load-bearing reliability poll: reads a module var, no network.
const GRACE_MS = 1500; // canon panel paints from the bus within this window in the healthy path.

// Pure diff line-classer — the canon DiffView recipe (ApprovalPanel.tsx), copied so
// this product file never imports from the frozen tree. Same diff-add/del/hunk/file
// classes the canon .approval-diff styles, reused verbatim here.
function diffKind(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-file';
  if (line.startsWith('@@')) return 'diff-hunk';
  if (line.startsWith('+')) return 'diff-add';
  if (line.startsWith('-')) return 'diff-del';
  return '';
}

function DiffView({ diff }) {
  return (
    <pre className="approval-guard-diff" aria-label="Proposed change">
      {diff.split('\n').map((line, index) => (
        <span key={index} className={diffKind(line)}>
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  );
}

export default function ApprovalSafetyNet() {
  // SSR-safe lazy init (pure client SPA; document always exists at render, but the
  // guard keeps the component honest if ever rendered without a DOM).
  const hasDom = typeof document !== 'undefined';

  // OWN truth, seeded from the persisted adapter source — never from a single event.
  const [pending, setPending] = useState(() => getPendingApproval());
  // Timestamp of the genuine null→token transition (drives the grace gate). Cleared
  // on resolve; restarted on a back-to-back DIFFERENT token (replay re-capture).
  const [pendingSince, setPendingSince] = useState(() =>
    getPendingApproval() ? Date.now() : null,
  );
  // null | 'authorize' | 'reject' — disables both buttons during a decision (canon parity).
  const [busy, setBusy] = useState(null);
  // Re-render tick so the grace gate re-evaluates without a state churn loop.
  const [, setTick] = useState(0);

  // Track the token across syncs so we only RESET the grace timer on a real token
  // CHANGE (null→token, or tokenA→tokenB) — not on every identical re-read.
  const tokenRef = useRef(getPendingApproval()?.token ?? null);

  // The single reconciler: re-read the persisted adapter truth and reconcile our
  // local state + the grace anchor. Idempotent; safe to call from any source.
  const sync = useCallback(() => {
    const next = getPendingApproval();
    const nextToken = next?.token ?? null;
    const prevToken = tokenRef.current;
    if (nextToken !== prevToken) {
      tokenRef.current = nextToken;
      // A NEW (or first) token starts/restarts the grace window; a resolve clears it.
      setPendingSince(nextToken ? Date.now() : null);
    }
    setPending(next);
  }, []);

  // (1) POLL — the load-bearing reliability fix. Even if every bus event is missed,
  // the surface appears within ~POLL_MS of the token persisting. Reads a module var.
  useEffect(() => {
    const id = setInterval(sync, POLL_MS);
    return () => clearInterval(id);
  }, [sync]);

  // (2) BUS — instant reaction in the common case (same subscriber the HUD uses).
  useEffect(() => {
    const unsub = subscribeCognition((e) => {
      if (!e) return;
      if (e.type === 'approval-required' || e.type === 'approval-resolved') sync();
    });
    return unsub;
  }, [sync]);

  // (3) VISIBILITY / FOCUS — operator tabs back to a hung run → resolves immediately.
  useEffect(() => {
    const onVis = () => sync();
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('focus', onVis);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('focus', onVis);
    };
  }, [sync]);

  // Grace ticker: while a token is held but still inside the grace window, re-render
  // once the window elapses so the gate flips to "render". Off when nothing pends or
  // the window has already passed (no idle interval).
  const withinGrace = pending && pendingSince != null && Date.now() - pendingSince < GRACE_MS;
  useEffect(() => {
    if (!withinGrace) return undefined;
    const remaining = Math.max(0, GRACE_MS - (Date.now() - pendingSince));
    const id = setTimeout(() => setTick((t) => t + 1), remaining + 16);
    return () => clearTimeout(id);
  }, [withinGrace, pendingSince]);

  const authorize = useCallback(() => {
    setBusy('authorize');
    // approvePendingApproval() sets pendingApproval = null synchronously at entry
    // (before any await) — sync NOW for an optimistic clear so the surface vanishes
    // the instant the click lands, not after the network round-trip.
    const p = approvePendingApproval();
    sync();
    void Promise.resolve(p).finally(() => {
      setBusy(null);
      sync();
    });
  }, [sync]);

  const reject = useCallback(() => {
    setBusy('reject');
    const p = rejectPendingApproval();
    sync(); // optimistic clear — rejectPendingApproval() also nulls the token at entry.
    void Promise.resolve(p).finally(() => {
      setBusy(null);
      sync();
    });
  }, [sync]);

  if (!hasDom) return null;
  // Render nothing in the healthy path: no token, or still inside the grace window
  // (the canon panel paints from the bus event here, the operator acts, the token
  // clears, and this guard NEVER paints → zero double UI).
  if (!pending) return null;
  if (pendingSince != null && Date.now() - pendingSince < GRACE_MS) return null;

  const kindLabel = pending.kind && pending.kind !== 'other' ? ` · ${pending.kind.toUpperCase()}` : '';
  const pathLabel = pending.filepath ? ` · ${pending.filepath}` : '';

  const card = (
    <div className="approval-guard" data-z="62">
      <section
        className="approval-guard-card"
        role="alertdialog"
        aria-label="Resolve pending approval"
      >
        <header className="approval-guard-head">
          <span className="approval-guard-eyebrow">recovered from a missed approval signal</span>
          <span className="approval-guard-title">
            RESOLVE PENDING APPROVAL{kindLabel}{pathLabel}
          </span>
          <span className="approval-guard-summary">{pending.summary}</span>
        </header>

        {pending.explanation ? (
          <p className="approval-guard-explanation">{pending.explanation}</p>
        ) : null}

        {pending.diff ? (
          <DiffView diff={pending.diff} />
        ) : pending.command ? (
          <pre className="approval-guard-diff approval-guard-command">{pending.command}</pre>
        ) : null}

        <div className="approval-guard-actions">
          <button
            type="button"
            className="approval-guard-authorize"
            onClick={authorize}
            disabled={busy !== null}
          >
            {busy === 'authorize' ? 'EXECUTING…' : 'AUTHORIZE'}
          </button>
          <button
            type="button"
            className="approval-guard-reject"
            onClick={reject}
            disabled={busy !== null}
          >
            {busy === 'reject' ? 'STANDING DOWN…' : 'REJECT'}
          </button>
        </div>
        <i className="glass-grain" aria-hidden="true" />
      </section>
    </div>
  );

  return createPortal(card, document.body);
}
