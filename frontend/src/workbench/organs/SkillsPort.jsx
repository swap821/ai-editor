import { useState, useEffect, useCallback } from 'react';
import { getKnownTrails, getLinkState, trailLabel } from '../../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';

/* ─── SKILLS PORT · VERIFIED WORKFLOWS ─────────────────────────────────────────
   The brain's learned, reusable workflows — the stigmergy trail library. A trail
   is a goal-pattern the brain solved once and laid down; it is VERIFIED only when
   the brain re-used it successfully on a fresh goal. The reuse evidence is the
   load-bearing "generalization" signal here. Read-only.

   Data: ZERO new fetch. The typed adapter already polls the live pheromone map
   every ~20s (getKnownTrails()). We seed synchronously from that cache for an
   instant first paint, then re-read on the adapter's own `telemetry` bus event
   (its post-poll signal) — no HTTP, no timer in this port. Offline is read from
   the adapter's link state (getLinkState()), not a local fetch. Honest empty
   (brain learned nothing yet) is distinct from offline (AI-OS unreachable).
   ──────────────────────────────────────────────────────────────────────────── */

// status → row truth-state class. 'superseded' is neutral (a posture, not a fault);
// quarantined (handled separately) overrides everything as a fault signal.
const STATUS_CLASS = { verified: 'ok', candidate: 'busy', superseded: '' };
const STATUS_ORDER = { verified: 0, candidate: 1, superseded: 2 };

function Row({ trail }) {
  const quarantined = trail.quarantined === true;
  // A quarantined trail is a fault — red rail overrides its status color.
  const cls = quarantined ? 'bad' : STATUS_CLASS[trail.status] ?? '';
  const reuseTotal = (trail.reuse_success_count ?? 0) + (trail.reuse_failure_count ?? 0);
  const eyebrow = `${String(trail.status || '').toLowerCase()} · strength ${(
    trail.strength ?? 0
  ).toFixed(2)} · fresh ${(trail.freshness ?? 0).toFixed(2)}`;
  return (
    <div className={`organs-row organs-row--${cls}`} data-status={trail.status}>
      <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
      <div className="organs-row-main">
        <div className="organs-row-label">
          <span className="organs-row-name">{trailLabel(trail.goal_pattern)}</span>
          {quarantined && (
            <span className="organs-quar" title="Quarantined — this trail is a fault signal and is held out of reuse.">
              QUARANTINED
            </span>
          )}
        </div>
        <span className="organs-row-eyebrow">{eyebrow}</span>
      </div>
      <div className="organs-row-stats">
        <span>
          <span className="organs-stat-ok">✓{trail.success_count ?? 0}</span>
          {trail.failure_count > 0 && (
            <>
              {' '}
              <span className="organs-stat-fail">✗{trail.failure_count}</span>
            </>
          )}
        </span>
        <span
          className={`organs-stat-streak${
            (trail.reuse_success_count ?? 0) > 0 ? ' organs-stat-streak--ok' : ''
          }`}
          title="Reuse evidence — successful re-applications of this workflow on fresh goals."
        >
          reuse {trail.reuse_success_count ?? 0}/{reuseTotal}
        </span>
      </div>
    </div>
  );
}

export default function SkillsPort() {
  // Synchronous seed from the adapter's already-polled cache → instant first paint.
  const seed = getKnownTrails();
  const [rows, setRows] = useState(seed.length ? [...seed] : null);
  // loading (no poll yet) | live | empty (polled, brain has none) | offline.
  const [phase, setPhase] = useState(seed.length ? 'live' : 'loading');

  const reread = useCallback(() => {
    const trails = getKnownTrails();
    // Offline is derived from the adapter's link, never fabricated. If the link is
    // down keep the last-known rows (stale) and only flag offline when we have none.
    if (!getLinkState()) {
      setRows((prev) => {
        if (prev && prev.length) {
          setPhase('stale');
          return prev;
        }
        setPhase('offline');
        return prev;
      });
      return;
    }
    setRows([...trails]);
    setPhase(trails.length ? 'live' : 'empty');
  }, []);

  useEffect(() => {
    // The adapter owns the poll; its `telemetry` event is our re-read trigger.
    const unsub = subscribeCognition((e) => {
      if (!e) return;
      if (e.type === 'telemetry') {
        reread();
        return;
      }
      // Best-effort immediate freshness on a learn/master signal (the underlying
      // array updates on the next poll, so this is opportunistic only).
      const label = String(e.label || '');
      if (e.type === 'knowledge-acquired' || /^SKILL MASTERED/.test(label)) {
        reread();
      }
    });
    return unsub;
  }, [reread]);

  if (phase === 'loading' && rows === null) {
    return (
      <section aria-label="Verified workflows">
        <p className="organs-port-title">Verified Workflows</p>
        <div className="organs-skel" aria-hidden="true" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  if (phase === 'offline' && (rows === null || rows.length === 0)) {
    return (
      <section aria-label="Verified workflows">
        <p className="organs-port-title">Verified Workflows</p>
        <p className="organs-note organs-note--offline">
          WORKFLOWS OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  const list = Array.isArray(rows) ? rows : [];

  // Sort: status order, quarantined sinks to the bottom; within a group strength desc.
  const sorted = [...list].sort((a, b) => {
    const qa = a.quarantined === true ? 1 : 0;
    const qb = b.quarantined === true ? 1 : 0;
    if (qa !== qb) return qa - qb;
    const sa = STATUS_ORDER[a.status] ?? 9;
    const sb = STATUS_ORDER[b.status] ?? 9;
    if (sa !== sb) return sa - sb;
    return (b.strength ?? 0) - (a.strength ?? 0);
  });

  // Divider between status groups (quarantined treated as its own trailing group).
  const groupKey = (t) => (t.quarantined === true ? 'quarantined' : t.status);
  const rendered = [];
  let prevKey = null;
  for (const trail of sorted) {
    const key = groupKey(trail);
    if (prevKey !== null && key !== prevKey) {
      rendered.push(<hr key={`div-${trail.skill_id}`} className="organs-divider" />);
    }
    rendered.push(<Row key={trail.skill_id} trail={trail} />);
    prevKey = key;
  }

  return (
    <section aria-label="Verified workflows">
      <p className="organs-port-title">
        Verified Workflows
        {phase === 'stale' && <span className="organs-stale">· stale</span>}
      </p>
      {list.length === 0 ? (
        <p className="organs-note">
          No verified workflows yet. The brain lays a trail when it solves a goal,
          and verifies it on re-use.
        </p>
      ) : (
        <div>{rendered}</div>
      )}
    </section>
  );
}
