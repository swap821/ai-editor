/**
 * SovereignStatePanel — the operator's live dominion, in one read-out.
 *
 * The backend has carried these sovereignty surfaces for weeks with zero UI:
 * the earned-autonomy ledger (with the README's promised one-click revoke),
 * the quarantined fact-proposal queue, the pheromone trail map, and the mined
 * curriculum proposals. This panel wires all four, read-only except the
 * explicitly human actions each surface was designed around (revoke, fact
 * approve/reject, curriculum accept).
 *
 * Rendered inside the CouncilDashboard aside (its "Sovereign State" tab) and
 * styled entirely with existing council-dashboard classes — no new palette.
 */
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Cloud, FileText, ShieldCheck } from 'lucide-react';
import {
  approveFactProposal,
  fetchPendingFacts,
  rejectFactProposal,
} from '../superbrain/lib/aiosAdapter';
import { API_BASE, API_HEADERS } from '../config';

async function getJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postAction(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

const AUTONOMY_TONE = { earned: 'ok', probation: 'warn', revoked: 'danger' };

function resourceTone(mode) {
  if (mode === 'normal') return 'ok';
  if (mode === 'conservation' || mode === 'hibernation') return 'warn';
  return 'danger';
}

function collectCasteCounts(council) {
  const counts = {};
  asArray(council?.missions).forEach((mission) => {
    const decree = mission.royalDecree || {};
    const contracts = [decree.scout_contract, ...asArray(decree.worker_contracts)];
    contracts.forEach((contract) => {
      const caste = contract?.metadata?.caste;
      if (!caste) return;
      counts[caste] = (counts[caste] || 0) + 1;
    });
  });
  return Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
}

function pendingProposalCount({ facts, curriculum, council, selfAnalysis }) {
  const pendingApprovals = asArray(council?.missions).reduce(
    (total, mission) => total + asArray(mission.pendingApprovals).length,
    0,
  );
  const selfAnalysisPending = asArray(selfAnalysis?.proposals).filter((proposal) => (
    proposal?.status || 'proposed'
  ) === 'proposed').length;
  return facts.length + curriculum.length + pendingApprovals + selfAnalysisPending;
}

export default function SovereignStatePanel() {
  const [autonomy, setAutonomy] = useState(null);
  const [facts, setFacts] = useState([]);
  const [trails, setTrails] = useState(null);
  const [curriculum, setCurriculum] = useState([]);
  const [v7, setV7] = useState({
    repoMap: null,
    resource: null,
    hibernation: null,
    pheromones: null,
    council: null,
    selfAnalysis: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyKey, setBusyKey] = useState('');

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    // Independent reads; one failing section must not blank the others.
    // Facts ride the adapter's existing quarantine helper (shared with the
    // memory halo) instead of a re-implemented fetch.
    const results = await Promise.allSettled([
      getJson('/api/v1/development/autonomy', signal),
      fetchPendingFacts(),
      getJson('/api/v1/development/trails', signal),
      getJson('/api/v1/development/curriculum/proposals', signal),
      getJson('/api/v1/projects/passport/status', signal),
      getJson('/api/v1/resource/status', signal),
      getJson('/api/v1/hibernation/status', signal),
      getJson('/api/v1/pheromones/surface', signal),
      getJson('/api/v1/council/missions?limit=8', signal),
      getJson('/api/v1/self-analysis/proposals', signal),
    ]);
    // An aborted load is a CANCELLED load (unmount / StrictMode cleanup), not
    // a failure: bail before any setState, or the abandoned first pass would
    // overwrite the live pass's state (e.g. paint 'offline' over real data).
    if (results.some((r) => r.status === 'rejected' && r.reason?.name === 'AbortError')) {
      return;
    }
    const [
      autonomyR,
      factsR,
      trailsR,
      curriculumR,
      repoMapR,
      resourceR,
      hibernationR,
      pheromonesR,
      councilR,
      selfAnalysisR,
    ] = results;
    if (autonomyR.status === 'fulfilled') setAutonomy(autonomyR.value);
    if (factsR.status === 'fulfilled') setFacts(asArray(factsR.value));
    if (trailsR.status === 'fulfilled') setTrails(trailsR.value);
    if (curriculumR.status === 'fulfilled') setCurriculum(asArray(curriculumR.value.proposals));
    setV7({
      repoMap: repoMapR.status === 'fulfilled' ? repoMapR.value : null,
      resource: resourceR.status === 'fulfilled' ? resourceR.value : null,
      hibernation: hibernationR.status === 'fulfilled' ? hibernationR.value : null,
      pheromones: pheromonesR.status === 'fulfilled' ? pheromonesR.value : null,
      council: councilR.status === 'fulfilled' ? councilR.value : null,
      selfAnalysis: selfAnalysisR.status === 'fulfilled' ? selfAnalysisR.value : null,
    });
    if (results.every((r) => r.status === 'rejected')) setError('Sovereign state link offline');
    setLoading(false);
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const act = useCallback(
    async (key, run) => {
      setBusyKey(key);
      setActionError('');
      try {
        await run();
        void load();
      } catch (err) {
        setActionError(err?.message || `Action failed: ${key}`);
      } finally {
        setBusyKey('');
      }
    },
    [load],
  );

  const entries = asArray(autonomy?.entries);
  const trailRows = asArray(trails?.trails).slice(0, 8);
  const repoMap = v7.repoMap;
  const resource = v7.resource;
  const hibernation = v7.hibernation;
  const pheromoneRows = asArray(v7.pheromones?.pheromones).slice(0, 4);
  const casteCounts = collectCasteCounts(v7.council);
  const pendingCount = pendingProposalCount({
    facts,
    curriculum,
    council: v7.council,
    selfAnalysis: v7.selfAnalysis,
  });
  const resourceMode = resource?.mode || 'unknown';
  const repoLastScan = repoMap?.lastScan;

  return (
    <div className="council-dashboard__body" aria-label="Sovereign state">
      {loading && !autonomy && facts.length === 0 && !trails ? (
        <div className="council-dashboard__empty">Reading the sovereign ledgers…</div>
      ) : error ? (
        <div className="council-dashboard__empty">{error}</div>
      ) : (
        <div className="council-dashboard__detail">
          <section className="council-dashboard__section" aria-label="V7 truth surface">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Sovereign Superorganism v7
              <span className={`council-dashboard__badge is-${repoMap?.localOnly ? 'ok' : 'warn'}`}>
                {repoMap?.localOnly ? 'local only' : 'status partial'}
              </span>
              <span className={`council-dashboard__badge is-${resourceTone(resourceMode)}`}>
                {resourceMode}
              </span>
            </h3>
            <div className="council-dashboard__grid">
              <span>
                <b>RepoMap</b>
                {repoMap
                  ? repoLastScan
                    ? `${String(repoLastScan.purpose || 'scanned').slice(0, 54)} · ${repoMap.activation}`
                    : `ready · ${repoMap.activation}`
                  : 'offline'}
              </span>
              <span>
                <b>Resource</b>
                {resource
                  ? `${resourceMode} · ${resource.cloud_allowed ? 'cloud allowed' : 'cloud blocked'}`
                  : 'offline'}
              </span>
              <span>
                <b>Hibernation</b>
                {hibernation
                  ? hibernation.lastRun
                    ? `${hibernation.lastRun.proposalCount ?? 0} proposals · ${hibernation.lastRun.cloudCalls ?? 0} cloud calls`
                    : 'not run · writes/cloud blocked'
                  : 'offline'}
              </span>
              <span>
                <b>Pheromones</b>
                {v7.pheromones ? `${pheromoneRows.length} advisory signal(s)` : 'disabled or offline'}
              </span>
              <span>
                <b>Caste contracts</b>
                {casteCounts.length
                  ? casteCounts.map(([caste, count]) => `${caste} x${count}`).join(', ')
                  : 'none contracted'}
              </span>
              <span>
                <b>Pending proposals</b>
                {pendingCount} pending item(s)
              </span>
            </div>
            <p className="council-dashboard__muted">
              RepoMap and pheromones are proposal evidence only; security, verification, and King approval stay authoritative.
            </p>
            {pheromoneRows.length ? (
              <div className="council-dashboard__route" aria-label="Pheromone trails">
                {pheromoneRows.map((trail) => (
                  <span key={`${trail.type}-${trail.resource}-${trail.id}`}>
                    {trail.type} · {String(trail.resource).slice(0, 42)} · {Math.round((trail.strength ?? 0) * 100)}%
                  </span>
                ))}
              </div>
            ) : null}
          </section>

          <section className="council-dashboard__section" aria-label="Earned autonomy ledger">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Earned Autonomy
              {autonomy ? (
                <span className={`council-dashboard__badge is-${autonomy.enabled ? 'ok' : 'warn'}`}>
                  {autonomy.enabled ? `armed · floor ${autonomy.min_successes}` : 'disabled'}
                </span>
              ) : null}
            </h3>
            {entries.length === 0 ? (
              <p>No action class has earned autonomy — every write still pauses for you.</p>
            ) : (
              entries.map((entry) => (
                <div key={entry.signature} className="council-dashboard__route">
                  <span className={`council-dashboard__badge is-${AUTONOMY_TONE[entry.status] || 'warn'}`}>
                    {entry.status}
                  </span>
                  <span>
                    {entry.action_type} · {entry.target_shape} · streak {entry.streak} (
                    {entry.success_count}✓/{entry.failure_count}✗)
                  </span>
                  {entry.status !== 'revoked' ? (
                    <button
                      type="button"
                      disabled={busyKey === entry.signature}
                      onClick={() =>
                        act(entry.signature, () =>
                          postAction(
                            `/api/v1/development/autonomy/revoke?signature=${encodeURIComponent(entry.signature)}`,
                          ),
                        )
                      }
                    >
                      Revoke
                    </button>
                  ) : null}
                </div>
              ))
            )}
          </section>

          <section className="council-dashboard__section" aria-label="Pending fact proposals">
            <h3>
              <AlertTriangle size={14} aria-hidden="true" /> Facts Awaiting Your Review
            </h3>
            {facts.length === 0 ? (
              <p>Quarantine is empty — nothing waits to become knowledge.</p>
            ) : (
              facts.map((fact) => (
                <div key={fact.id} className="council-dashboard__route">
                  <span>
                    {fact.subject} — {fact.predicate} — {fact.object}
                  </span>
                  <button
                    type="button"
                    disabled={busyKey === `fact-${fact.id}`}
                    onClick={() =>
                      act(`fact-${fact.id}`, async () => {
                        // Adapter helper: sends the required resolvedBy and
                        // maps the backend's 409 to a contradiction verdict.
                        const result = await approveFactProposal(fact.id);
                        if (result === 'contradiction') {
                          throw new Error(
                            `Fact #${fact.id} contradicts active knowledge — it stays pending for reconcile.`,
                          );
                        }
                        if (result !== 'approved') throw new Error(`Could not approve fact #${fact.id}`);
                      })
                    }
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busyKey === `fact-${fact.id}`}
                    onClick={() =>
                      act(`fact-${fact.id}`, async () => {
                        const ok = await rejectFactProposal(fact.id);
                        if (!ok) throw new Error(`Could not reject fact #${fact.id}`);
                      })
                    }
                  >
                    Reject
                  </button>
                </div>
              ))
            )}
          </section>

          <section className="council-dashboard__section" aria-label="Skill trails">
            <h3>
              <Cloud size={14} aria-hidden="true" /> Skill Trails
              {trails?.summary ? (
                <span className="council-dashboard__badge is-ok">
                  {trails.summary.verified ?? 0} verified · {trails.summary.candidate ?? 0} candidate
                </span>
              ) : null}
            </h3>
            {trailRows.length === 0 ? (
              <p>No trails yet — experience is still being earned.</p>
            ) : (
              trailRows.map((trail, index) => (
                <div key={trail.skill_id ?? index} className="council-dashboard__route">
                  <span className={`council-dashboard__badge is-${trail.status === 'verified' ? 'ok' : 'warn'}`}>
                    {trail.quarantined ? 'quarantined' : trail.status}
                  </span>
                  <span>{String(trail.goal_pattern ?? trail.goal ?? '').slice(0, 64)}</span>
                  <span>{Math.round((trail.strength ?? 0) * 100)}%</span>
                </div>
              ))
            )}
          </section>

          <section className="council-dashboard__section" aria-label="Curriculum proposals">
            <h3>
              <FileText size={14} aria-hidden="true" /> Curriculum Proposals
            </h3>
            {curriculum.length === 0 ? (
              <p>No mined proposals — the curriculum is current.</p>
            ) : (
              curriculum.map((proposal) => (
                <div key={proposal.fingerprint} className="council-dashboard__route">
                  <span>
                    {proposal.skill_name} L{proposal.level}: {String(proposal.prompt).slice(0, 64)}
                  </span>
                  <button
                    type="button"
                    disabled={busyKey === proposal.fingerprint}
                    onClick={() =>
                      act(proposal.fingerprint, () =>
                        postAction('/api/v1/development/curriculum/proposals/accept', {
                          fingerprint: proposal.fingerprint,
                        }),
                      )
                    }
                  >
                    Accept
                  </button>
                </div>
              ))
            )}
          </section>

          {actionError ? <p className="council-dashboard__error">{actionError}</p> : null}
        </div>
      )}
    </div>
  );
}
