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
import { AlertTriangle, Cloud, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
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


function scanSummary(surface) {
  if (!surface) return 'offline';
  if (!surface.lastScan) return 'not scanned';
  return `${surface.lastScan.findingCount ?? 0} finding(s) · ${surface.lastScan.cloudCalls ?? 0} cloud calls`;
}

function repoMapSummary(surface) {
  if (!surface) return 'offline';
  if (!surface.lastScan) return 'not scanned';
  return `${surface.lastScan.symbolCount ?? 0} symbols · ${surface.activation}`;
}

/** A MetricEnvelope-shaped field: {value, status, source, ...}. Renders the
 * real value when measured, an honest "unavailable" when not -- never a
 * silently-guessed default. */
function envelopeText(envelope, formatValue = (v) => String(v)) {
  if (!envelope || envelope.status !== 'measured') return 'unavailable';
  return formatValue(envelope.value);
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
  const [v10, setV10] = useState(null);
  const [governance, setGovernance] = useState(null);
  const [executor, setExecutor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyKey, setBusyKey] = useState('');
  const [manualRefreshing, setManualRefreshing] = useState(false);

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
      getJson('/api/v1/v10/status', signal),
      getJson('/api/v1/mirror/governance', signal),
      getJson('/api/v1/mirror/executor', signal),
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
      v10R,
      governanceR,
      executorR,
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
    setV10(v10R.status === 'fulfilled' ? v10R.value : null);
    setGovernance(governanceR.status === 'fulfilled' ? governanceR.value : null);
    setExecutor(executorR.status === 'fulfilled' ? executorR.value?.executor : null);
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
  const constitution = v10?.constitution;
  const metaLoop = v10?.metaLoop;
  const councilMemory = v10?.councilMemory;

  return (
    <div className="council-dashboard__body" aria-label="Sovereign state">
      {loading && !autonomy && facts.length === 0 && !trails ? (
        <div className="council-dashboard__empty">Reading the sovereign ledgers…</div>
      ) : error ? (
        <div className="council-dashboard__empty">{error}</div>
      ) : (
        <div className="council-dashboard__detail">
          <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '4px 2px 0' }}>
            <button
              type="button"
              className={`council-dashboard__icon-btn${manualRefreshing ? ' is-refreshing' : ''}`}
              onClick={() => {
                setManualRefreshing(true);
                load().finally(() => setManualRefreshing(false));
              }}
              aria-label="Refresh sovereign state"
              title="Refresh"
            >
              <RefreshCw size={16} aria-hidden="true" />
            </button>
          </div>

          <section className="council-dashboard__section" aria-label="V10 truth surface">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Sovereign Organism v10
              <span className={`council-dashboard__badge is-${v10?.localOnly ? 'ok' : 'warn'}`}>
                {v10?.localOnly ? 'local only' : 'offline'}
              </span>
              <span className="council-dashboard__badge is-warn">
                {v10?.authority || 'proposal/evidence'}
              </span>
            </h3>
            <div className="council-dashboard__grid">
              <span>
                <b>Constitution</b>
                {constitution
                  ? `${constitution.casteCount ?? 0} castes · ${constitution.frozenCoreProtected ? 'frozen core protected' : 'frozen core unknown'}`
                  : 'offline'}
              </span>
              <span>
                <b>Vulture</b>
                {scanSummary(v10?.vulture)}
              </span>
              <span>
                <b>Ecosystem</b>
                {scanSummary(v10?.ecosystem)}
              </span>
              <span>
                <b>Council memory</b>
                {councilMemory ? `${councilMemory.deliberationCount ?? 0} deliberation(s)` : 'offline'}
              </span>
              <span>
                <b>Symbol RepoMap</b>
                {repoMapSummary(v10?.symbolRepoMap)}
              </span>
              <span>
                <b>Meta-loop</b>
                {metaLoop
                  ? `${metaLoop.safetyStatus} · ${metaLoop.proposalCount ?? 0} proposal(s)`
                  : 'offline'}
              </span>
            </div>
            <p className="council-dashboard__muted">
              These v10 organs are backend-backed advisory evidence; none can authorize action, mutate policy, self-apply, write files, or bypass approval.
            </p>
          </section>

          <section className="council-dashboard__section" aria-label="Constitution and emergency stop, measured">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Constitution &amp; Emergency Stop
              <span className={`council-dashboard__badge is-${governance?.emergencyStop?.engaged?.value ? 'danger' : 'ok'}`}>
                {governance?.emergencyStop?.engaged?.value ? 'STOPPED' : 'operational'}
              </span>
            </h3>
            <p className="council-dashboard__muted">
              Distinct from the v10 section's own "Constitution" field above
              (an older, separate caste-count view) — this is the typed,
              digest-verified read-model surface (organs 47/48): every field
              below is either a real measured value or an honest
              "unavailable", never guessed.
            </p>
            <div className="council-dashboard__grid">
              <span>
                <b>Constitution version</b>
                {envelopeText(governance?.constitution?.version)}
              </span>
              <span>
                <b>Ratified by</b>
                {envelopeText(governance?.constitution?.ratified_by_operator_id)}
              </span>
              <span>
                <b>Snapshot digest</b>
                {envelopeText(governance?.constitution?.snapshot_digest, (v) => `${String(v).slice(0, 16)}…`)}
              </span>
              <span>
                <b>Foundation laws</b>
                {envelopeText(governance?.constitution?.foundation_laws_count)}
              </span>
              <span>
                <b>Emergency stop</b>
                {envelopeText(governance?.emergencyStop?.engaged, (v) => (v ? 'engaged' : 'clear'))}
              </span>
              <span>
                <b>Stop reason</b>
                {envelopeText(governance?.emergencyStop?.reason)}
              </span>
            </div>
          </section>

          <section className="council-dashboard__section" aria-label="Provider health, measured">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Provider Health
              <span className="council-dashboard__badge is-ok">
                {(governance?.providerHealth ?? []).length} observed
              </span>
            </h3>
            <p className="council-dashboard__muted">
              Only providers with at least one real recorded call outcome are shown — a never-called provider is never presented as "healthy".
            </p>
            {(governance?.providerHealth ?? []).length === 0 ? (
              <p>No provider calls observed yet this process.</p>
            ) : (
              (governance?.providerHealth ?? []).map((p) => (
                <div key={p.provider} className="council-dashboard__route">
                  <span className={`council-dashboard__badge is-${p.reachable?.value ? 'ok' : 'danger'}`}>
                    {envelopeText(p.circuit_state)}
                  </span>
                  <span>
                    {p.provider} · {envelopeText(p.recent_failure_count)} recent failure(s)
                  </span>
                </div>
              ))
            )}
          </section>

          <section className="council-dashboard__section" aria-label="Pending approvals, measured">
            <h3>
              <AlertTriangle size={14} aria-hidden="true" /> Pending Approvals
              <span className="council-dashboard__badge is-warn">
                {(governance?.approvals ?? []).length} pending
              </span>
            </h3>
            <p className="council-dashboard__muted">
              A real, read-only enumeration of every capability awaiting consumption (CapabilityAuthority) — never exposes a usable bearer token.
            </p>
            {(governance?.approvals ?? []).length === 0 ? (
              <p>Nothing awaiting consumption right now.</p>
            ) : (
              (governance?.approvals ?? []).map((a, index) => (
                <div key={index} className="council-dashboard__route">
                  <span>{envelopeText(a.requested_action)}</span>
                  <span>{envelopeText(a.mission_id)}</span>
                  <span>{envelopeText(a.scope)}</span>
                </div>
              ))
            )}
          </section>

          <section className="council-dashboard__section" aria-label="Routing decisions, measured">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Provenance &amp; Explanation
              <span className="council-dashboard__badge is-ok">
                {(governance?.routingDecisions ?? []).length} recent turn(s)
              </span>
            </h3>
            <p className="council-dashboard__muted">
              Why the router picked a model, for the most recent real turns — sourced from durably recorded routing metadata, never guessed.
            </p>
            {(governance?.routingDecisions ?? []).length === 0 ? (
              <p>No routed turn recorded yet this session.</p>
            ) : (
              (governance?.routingDecisions ?? []).map((d, index) => (
                <div key={index} className="council-dashboard__route">
                  <span className={`council-dashboard__badge is-${envelopeText(d.privacy) === 'cloud' ? 'warn' : 'ok'}`}>
                    {envelopeText(d.privacy)}
                  </span>
                  <span>
                    {envelopeText(d.provider)} · {envelopeText(d.model)} · {envelopeText(d.task)}
                  </span>
                  <span>{envelopeText(d.recorded_at)}</span>
                </div>
              ))
            )}
            <p className="council-dashboard__muted" style={{ marginTop: '8px' }}>
              What was sent / what was removed before a cloud call — real per-call redaction counts, never a second logging sink.
            </p>
            {(governance?.privacyAudits ?? []).length === 0 ? (
              <p>No cloud call audited yet this session.</p>
            ) : (
              (governance?.privacyAudits ?? []).map((a, index) => (
                <div key={index} className="council-dashboard__route" aria-label="Privacy audit">
                  <span>{envelopeText(a.provider)}</span>
                  <span>
                    {envelopeText(a.redacted_paths)} path(s) · {envelopeText(a.redacted_credentials)} credential(s) · {envelopeText(a.redacted_secrets)} secret(s)
                  </span>
                  <span>{envelopeText(a.recorded_at)}</span>
                </div>
              ))
            )}
          </section>

          <section className="council-dashboard__section" aria-label="Isolated executor, measured">
            <h3>
              <ShieldCheck size={14} aria-hidden="true" /> Isolated Executor
              <span
                className={`council-dashboard__badge is-${
                  executor?.reachable?.value ? 'ok' : executor?.configured?.value ? 'danger' : 'warn'
                }`}
              >
                {executor?.reachable?.value
                  ? 'reachable'
                  : executor?.configured?.value
                    ? 'unreachable'
                    : 'not configured'}
              </span>
            </h3>
            <div className="council-dashboard__grid">
              <span>
                <b>Configured</b>
                {envelopeText(executor?.configured, (v) => (v ? 'yes' : 'no'))}
              </span>
              <span>
                <b>Reachable</b>
                {envelopeText(executor?.reachable, (v) => (v ? 'yes' : 'no'))}
              </span>
              <span>
                <b>Runtime</b>
                {envelopeText(executor?.runtime)}
              </span>
              <span>
                <b>Reason</b>
                {envelopeText(executor?.reason)}
              </span>
            </div>
          </section>

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
