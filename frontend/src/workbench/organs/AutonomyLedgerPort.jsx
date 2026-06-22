import { useState, useEffect, useCallback, useRef } from 'react';
import { AIOS_BASE, getAutonomy } from '../../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';
import { API_HEADERS } from '../../config';

/* ─── AUTONOMY LEDGER PORT ─────────────────────────────────────────────────────
   Read-only observability of the brain's EARNED grown-up capabilities — which
   YELLOW action classes have graduated to autonomous execution by repeated
   verified success, which are on probation accruing evidence, which were revoked.

   Data: a DIRECT GET to the rich endpoint (the typed adapter snapshot drops
   failure_count + the timestamps), seeded synchronously from getAutonomy() for an
   instant first paint with no blank flash. Best-effort refresh on open + on the
   real CAPABILITY EARNED / AUTONOMOUS ACTION bus events (bounded burst, no
   continuous poll). Honest offline: keep the last seed with a `· stale` tag, never
   fabricate a row.

   Read-only by design: the /revoke POST exists but force-revoke is a sovereignty
   action kept OUT of this observability organ (no accidental destructive control).
   ──────────────────────────────────────────────────────────────────────────── */

// The rich ledger endpoint is on the SAME backend as the adapter (AIOS_BASE) and
// the product config (API_BASE) — both resolve to one boundary via vite.config's
// `define`. Reuse the product's API_HEADERS (VITE_AIOS_API_TOKEN) for auth so this
// port carries the same Bearer the rest of the product does, with no re-derivation.
const fmtDate = (iso) => {
  if (!iso) return '';
  const d = new Date(String(iso).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.toISOString().slice(0, 10);
};

const STATUS_CLASS = { earned: 'ok', probation: 'busy', revoked: 'bad' };
const STATUS_ORDER = { earned: 0, probation: 1, revoked: 2 };

function Row({ entry, minSuccesses }) {
  const status = entry.status;
  const cls = STATUS_CLASS[status] || '';
  const action = `${entry.action_type || ''} ${entry.target_shape || ''}`.trim();
  let eyebrow;
  if (status === 'earned') eyebrow = `earned · ${fmtDate(entry.earned_at)}`;
  else if (status === 'probation') eyebrow = `${entry.success_count}/${minSuccesses} to earn`;
  else if (status === 'revoked') eyebrow = `revoked · ${fmtDate(entry.revoked_at)}`;
  const showStreak =
    typeof entry.streak === 'number' && entry.streak > 0 && status !== 'revoked';
  return (
    <div className={`organs-row organs-row--${cls}`} data-status={status}>
      <span
        className={`organs-dot organs-dot--${cls}`}
        aria-hidden="true"
      />
      <div className="organs-row-main">
        <div className="organs-row-label">
          <span className="organs-row-name">{action || entry.signature}</span>
        </div>
        {eyebrow && <span className="organs-row-eyebrow">{eyebrow}</span>}
      </div>
      <div className="organs-row-stats">
        <span>
          <span className="organs-stat-ok">✓{entry.success_count ?? 0}</span>
          {entry.failure_count > 0 && (
            <>
              {' '}
              <span className="organs-stat-fail">✗{entry.failure_count}</span>
            </>
          )}
        </span>
        {showStreak && (
          <span
            className={`organs-stat-streak${status === 'earned' ? ' organs-stat-streak--ok' : ''}`}
          >
            ⚡streak {entry.streak}
          </span>
        )}
      </div>
    </div>
  );
}

export default function AutonomyLedgerPort() {
  // Synchronous seed → instant first paint (no blank flash).
  const seed = getAutonomy();
  const [data, setData] = useState(seed);
  const [phase, setPhase] = useState(seed ? 'seed' : 'loading'); // loading|seed|live|stale|offline
  const timersRef = useRef([]);
  // Whether we have ever shown real data (seed or a prior successful fetch). On a
  // later fetch failure this decides STALE (keep last good) vs OFFLINE.
  const hadDataRef = useRef(!!seed);

  const fetchLedger = useCallback(async () => {
    try {
      const r = await fetch(`${AIOS_BASE}/api/v1/development/autonomy`, {
        headers: API_HEADERS,
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      hadDataRef.current = true;
      setData(json);
      setPhase('live');
    } catch {
      // Keep the last good data with a stale tag; only declare OFFLINE if we never
      // had anything (no seed and no prior successful fetch).
      setPhase(hadDataRef.current ? 'stale' : 'offline');
    }
  }, []);

  useEffect(() => {
    fetchLedger();
    const unsub = subscribeCognition((e) => {
      if (!e || e.type === 'telemetry') return;
      const label = String(e.label || '');
      if (label === 'CAPABILITY EARNED' || label === 'AUTONOMOUS ACTION') {
        timersRef.current.forEach(clearTimeout);
        timersRef.current = [300, 1500].map((d) => setTimeout(fetchLedger, d));
      }
    });
    return () => {
      unsub();
      timersRef.current.forEach(clearTimeout);
    };
  }, [fetchLedger]);

  // Loading (no seed yet, fetch not resolved).
  if (phase === 'loading' && !data) {
    return (
      <section aria-label="Autonomy ledger">
        <p className="organs-port-title">Autonomy Ledger</p>
        <div className="organs-strip">
          <span className="organs-strip-item">
            <span className="organs-dot" /> MASTER SWITCH —
          </span>
          <span className="organs-strip-item organs-strip-spacer">THRESHOLD —</span>
        </div>
        <div className="organs-skel" aria-hidden="true" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  // Offline (never reached the backend, no seed).
  if (phase === 'offline' && !data) {
    return (
      <section aria-label="Autonomy ledger">
        <p className="organs-port-title">Autonomy Ledger</p>
        <p className="organs-note organs-note--offline">
          LEDGER OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  const enabled = !!data?.enabled;
  const minSuccesses =
    typeof data?.min_successes === 'number' ? data.min_successes : null;
  const entries = Array.isArray(data?.entries) ? data.entries : [];
  const summary = data?.summary || { earned: 0, probation: 0, revoked: 0 };

  const sorted = [...entries].sort((a, b) => {
    const sa = STATUS_ORDER[a.status] ?? 9;
    const sb = STATUS_ORDER[b.status] ?? 9;
    if (sa !== sb) return sa - sb;
    return (b.success_count ?? 0) - (a.success_count ?? 0);
  });

  // Group dividers between status groups.
  const rows = [];
  let prevStatus = null;
  for (const entry of sorted) {
    if (prevStatus !== null && entry.status !== prevStatus) {
      rows.push(<hr key={`div-${entry.signature}`} className="organs-divider" />);
    }
    rows.push(
      <Row key={entry.signature} entry={entry} minSuccesses={minSuccesses ?? '—'} />
    );
    prevStatus = entry.status;
  }

  return (
    <section aria-label="Autonomy ledger">
      <p className="organs-port-title">
        Autonomy Ledger
        {phase === 'stale' && <span className="organs-stale">· stale</span>}
      </p>

      <div
        className="organs-strip"
        title="Read-only ledger. Force-revoke is a separate sovereignty action."
      >
        <span className="organs-strip-item">
          <span className={`organs-dot organs-dot--${enabled ? 'ok' : ''}`} />
          MASTER SWITCH{' '}
          <b className={enabled ? 'organs-switch-state--on' : 'organs-switch-state--off'}>
            {enabled ? 'ENABLED' : 'DISABLED'}
          </b>
        </span>
        <span className="organs-strip-item organs-strip-spacer">
          THRESHOLD <b>{minSuccesses ?? '—'}</b>
        </span>
      </div>

      <div className="organs-chips" role="list">
        <span className="organs-chip organs-chip--ok" role="listitem">
          ⚡<b>{summary.earned ?? 0}</b> EARNED
        </span>
        <span className="organs-chip organs-chip--busy" role="listitem">
          ◐<b>{summary.probation ?? 0}</b> PROBATION
        </span>
        <span className="organs-chip organs-chip--bad" role="listitem">
          ⊘<b>{summary.revoked ?? 0}</b> REVOKED
        </span>
      </div>

      {!enabled && (
        <p className="organs-note">
          Earned autonomy is switched off — classes accrue evidence but never
          auto-act.
        </p>
      )}

      {entries.length === 0 ? (
        <p className="organs-note">
          No earned capabilities yet. The brain earns autonomy on a YELLOW action
          class after <b>{minSuccesses ?? 'N'}</b> verified successes.
        </p>
      ) : (
        <div>{rows}</div>
      )}
    </section>
  );
}
