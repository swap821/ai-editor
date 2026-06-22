import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';
import { truncate } from './_fmt';

/* ─── PROPOSALS PORT · SELF-ANALYSIS FINDINGS ──────────────────────────────────
   Read-only view of the self-improvement loop's open fix proposals — the findings
   the self-analysis agent filed but has NO power to apply. OBSERVE-FIRST: apply /
   reject are sovereignty actions, kept OUT of this observability organ (the classic
   ProposalsPanel owns them). This deliberately mirrors AutonomyLedgerPort omitting
   /revoke — no destructive control on the HUD layer.

   Data: a real GET /api/v1/self-analysis/proposals?status=proposed via the product
   config base/headers (same base+auth CurriculumPort + ProposalsPanel use).
   Refresh: on open + a single delayed catch-up, plus an opportunistic re-fetch on
   `knowledge-acquired` (the self-analysis loop emits no dedicated bus label, so we
   do NOT invent a poll). Honest offline: keep last good with a `· stale` tag.
   ──────────────────────────────────────────────────────────────────────────── */

// proposed_zone → row truth-state. RED = frozen-core, review-only — surfaced loudly
// as both a red rail AND a text pill (double-encoded). YELLOW is the ordinary case.
const ZONE_CLASS = { RED: 'bad', YELLOW: 'busy' };

function Row({ p }) {
  const zone = p.proposed_zone || 'YELLOW';
  const cls = ZONE_CLASS[zone] ?? 'busy';
  const red = zone === 'RED';
  return (
    <div className={`organs-row organs-row--${cls}`} data-zone={zone}>
      <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
      <div className="organs-row-main">
        <div className="organs-row-label">
          <span className="organs-row-name">{p.target_path}</span>
          {red && (
            <span className="organs-quar" title="RED — frozen security core; review-only, never auto-applied.">
              RED
            </span>
          )}
        </div>
        <span className="organs-row-eyebrow">
          {p.finding_type} · #{p.id}
        </span>
        {p.evidence && (
          <span className="organs-rung-prompt" title={p.evidence}>
            {truncate(p.evidence, 96)}
          </span>
        )}
      </div>
      <div className="organs-row-stats">
        <span className="organs-rung-status">{p.status}</span>
      </div>
    </div>
  );
}

export default function ProposalsPort() {
  const [rows, setRows] = useState(null); // null = not yet loaded
  const [phase, setPhase] = useState('loading'); // loading|live|stale|offline
  const timersRef = useRef([]);
  const hadDataRef = useRef(false);

  const fetchProposals = useCallback(async () => {
    try {
      const r = await fetch(
        `${API_BASE}/api/v1/self-analysis/proposals?status=proposed`,
        { headers: API_HEADERS }
      );
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      hadDataRef.current = true;
      setRows(Array.isArray(json.proposals) ? json.proposals : []);
      setPhase('live');
    } catch {
      setPhase(hadDataRef.current ? 'stale' : 'offline');
    }
  }, []);

  useEffect(() => {
    fetchProposals();
    // No dedicated self-analysis bus label exists; catch up once shortly after open,
    // and opportunistically re-fetch on a generic knowledge-acquired pulse. No poll.
    timersRef.current = [setTimeout(fetchProposals, 1500)];
    const unsub = subscribeCognition((e) => {
      if (!e || e.type === 'telemetry') return;
      if (e.type === 'knowledge-acquired') {
        timersRef.current.forEach(clearTimeout);
        timersRef.current = [300, 1500].map((d) => setTimeout(fetchProposals, d));
      }
    });
    return () => {
      unsub();
      timersRef.current.forEach(clearTimeout);
    };
  }, [fetchProposals]);

  if (phase === 'loading' && rows === null) {
    return (
      <section aria-label="Self-analysis proposals">
        <p className="organs-port-title">Self-Analysis · Proposals</p>
        <div className="organs-skel" aria-hidden="true" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  if (phase === 'offline' && rows === null) {
    return (
      <section aria-label="Self-analysis proposals">
        <p className="organs-port-title">Self-Analysis · Proposals</p>
        <p className="organs-note organs-note--offline">
          PROPOSALS OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  const list = Array.isArray(rows) ? rows : [];

  return (
    <section aria-label="Self-analysis proposals">
      <p className="organs-port-title">
        Self-Analysis · Proposals
        {phase === 'stale' && <span className="organs-stale">· stale</span>}
      </p>

      <div
        className="organs-strip"
        title="Apply/reject is a sovereignty action — kept out of this observability organ (Wave-3)."
      >
        <span className="organs-strip-item">
          OPEN PROPOSALS <b>{list.length}</b>
        </span>
        <span className="organs-strip-item organs-strip-spacer">OBSERVE-ONLY</span>
      </div>

      {list.length === 0 ? (
        <p className="organs-note">
          No open proposals. The self-analysis agent files a fix here when it finds
          one.
        </p>
      ) : (
        <div>
          {list.map((p) => (
            <Row key={p.id} p={p} />
          ))}
        </div>
      )}
    </section>
  );
}
