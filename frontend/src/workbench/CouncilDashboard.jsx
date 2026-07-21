import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Cloud, FileText, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';
import { ensureSession } from '../superbrain/lib/sessionId';
import SovereignStatePanel from './SovereignStatePanel';
import KnowledgeIngestPanel from './KnowledgeIngestPanel';
import MemoryOperationsPanel from './MemoryOperationsPanel';
import PolicyEnforcementHUD from './PolicyEnforcementHUD';
import SovereigntyControls from './SovereigntyControls';
import CouncilServicesPanel from './CouncilServicesPanel';
import RuntimeSurfaceHUD from './RuntimeSurfaceHUD';
import ExecutionDebuggerPanel from './ExecutionDebuggerPanel';
import AlignmentHUD from './AlignmentHUD';
import SecurityAuditPanel from './SecurityAuditPanel';
import './CouncilDashboard.css';

const EMPTY_DETAIL = { summary: null, report: null, ledger: null };

function titleCase(value) {
  return String(value || 'unknown').replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function verdictTone(verdict) {
  if (verdict === 'deny') return 'danger';
  if (verdict === 'defer' || verdict === 'allow_with_approval') return 'warn';
  return 'ok';
}

function riskTone(risk) {
  if (risk === 'RED') return 'danger';
  if (risk === 'YELLOW') return 'warn';
  return 'ok';
}

// Verification strength rendered as anatomy, not a table cell (The One Law): a
// strong verdict imprints brightly, a weak one is visibly faint, and a positive
// recommendation resting on below-floor evidence carries a caution at the decision
// point. Pure derive over either the detail report or the mission summary shape.
const STRENGTH_TONE = { STRONG: 'ok', MEDIUM: 'warn', WEAK: 'danger', NONE: 'danger' };
const STRENGTH_INTENSITY = { STRONG: 1, MEDIUM: 0.74, WEAK: 0.46, NONE: 0.3 };

function deriveVerificationStrength(report, summary) {
  const vr = (report && report.verification_result) || {};
  const level = vr.strength ?? summary?.verificationStrength ?? null;
  if (!level) return null; // no typed verification recorded (older mission)
  return {
    level,
    tone: STRENGTH_TONE[level] || 'danger',
    intensity: STRENGTH_INTENSITY[level] ?? 0.3,
    meetsFloor: (vr.meets_floor ?? summary?.verificationMeetsFloor) === true,
    warning: vr.below_floor_warning ?? summary?.verificationBelowFloorWarning ?? null,
  };
}

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, body) {
  const session = await ensureSession();
  const sessionBody = session.bodySessionId ? { sessionId: session.bodySessionId } : {};
  const request = (capability) => fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...API_HEADERS,
      ...(capability ? { 'X-AIOS-Capability': capability } : {}),
    },
    body: JSON.stringify({ ...sessionBody, ...body }),
  });
  let response = await request('');
  if (response.status === 428) {
    const detail = await response.json();
    const token = detail?.detail?.approvalToken;
    if (!token) throw new Error('HTTP 428');
    response = await request(token);
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

/** Self-Analysis findings review (T2 propose → HUMAN approve → T3 apply).
 *  The three endpoints existed with zero UI; this panel is the human-review
 *  surface the tier flow was built for. Apply is deliberately heavy: it is a
 *  gated write into aios/ (snapshot → verify → auto-rollback backend-side),
 *  so it confirms like the rollback button does. */
function SelfAnalysisProposals() {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [actionError, setActionError] = useState('');

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/self-analysis/proposals', signal);
      setProposals(asArray(data.proposals));
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Self-Analysis link offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const act = useCallback(
    async (id, action) => {
      if (
        action === 'apply' &&
        !window.confirm(`Apply proposal #${id} to aios/? (gated, verified, auto-rollback)`)
      ) {
        return;
      }
      setBusyId(id);
      setActionError('');
      try {
        await postJson(
          `/api/v1/self-analysis/proposals/${id}/${action}`,
          action === 'apply' ? { approvedBy: 'operator' } : {},
        );
        void load();
      } catch {
        setActionError(`Could not ${action} proposal #${id}`);
      } finally {
        setBusyId(null);
      }
    },
    [load],
  );

  return (
    <div className="council-dashboard__body" aria-label="Self-Analysis proposals">
      {proposals.length === 0 ? (
        <div className="council-dashboard__empty">
          {loading ? 'Syncing proposals' : error || 'No proposed findings'}
        </div>
      ) : (
        <div className="council-dashboard__detail">
          {proposals.map((p) => (
            <section key={p.id} className="council-dashboard__section" aria-label={`Proposal ${p.id}`}>
              <h3>
                <FileText size={14} aria-hidden="true" /> #{p.id} · {p.target_path}
              </h3>
              <p>
                <span className={`council-dashboard__badge is-${riskTone(p.proposed_zone)}`}>
                  {p.proposed_zone || 'YELLOW'}
                </span>{' '}
                {titleCase(p.finding_type)} · {titleCase(p.status)}
                {p.approved_by ? ` · approved by ${p.approved_by}` : ''}
              </p>
              {p.evidence ? <p>{String(p.evidence).slice(0, 240)}</p> : null}
              {p.proposed_diff ? (
                <pre className="council-dashboard__diff">{String(p.proposed_diff).slice(0, 1200)}</pre>
              ) : null}
              {p.status === 'proposed' ? (
                <div className="council-dashboard__decision-actions">
                  <button type="button" disabled={busyId === p.id} onClick={() => act(p.id, 'apply')}>
                    {busyId === p.id ? 'Working…' : 'Approve & apply'}
                  </button>
                  <button type="button" disabled={busyId === p.id} onClick={() => act(p.id, 'reject')}>
                    Reject
                  </button>
                </div>
              ) : null}
            </section>
          ))}
          {actionError ? <p className="council-dashboard__error">{actionError}</p> : null}
        </div>
      )}
    </div>
  );
}

export default function CouncilDashboard() {
  const [view, setView] = useState('missions');
  const [missions, setMissions] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(EMPTY_DETAIL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState('');
  const [rollbackBusy, setRollbackBusy] = useState(false);
  const [rollbackError, setRollbackError] = useState('');
  const [originGoal, setOriginGoal] = useState('');
  const [originFiles, setOriginFiles] = useState('');
  const [originVerification, setOriginVerification] = useState('');
  const [originBusy, setOriginBusy] = useState(false);
  const [originError, setOriginError] = useState('');

  const selectedSummary = useMemo(
    () => missions.find((mission) => mission.missionId === selectedId) || missions[0] || null,
    [missions, selectedId],
  );

  const loadMissions = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/council/missions?limit=8', signal);
      const rows = asArray(data.missions);
      setMissions(rows);
      setSelectedId((current) => {
        if (current && rows.some((row) => row.missionId === current)) return current;
        return rows[0]?.missionId || '';
      });
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Council link offline');
    } finally {
      setLoading(false);
    }
  }, []);

  const submitOrigination = useCallback(async () => {
    const goal = originGoal.trim();
    const allowedFiles = originFiles
      .split(/[\n,]/)
      .map((entry) => entry.trim())
      .filter(Boolean);
    const verificationCommands = originVerification
      .split('\n')
      .map((cmd) => cmd.trim())
      .filter(Boolean);
    if (!goal || allowedFiles.length === 0) {
      setOriginError('Goal and at least one allowed file are required');
      return;
    }
    setOriginBusy(true);
    setOriginError('');
    try {
      await postJson('/api/v1/council/missions', { goal, allowedFiles, verificationCommands });
      setOriginGoal('');
      setOriginFiles('');
      setOriginVerification('');
      void loadMissions();
    } catch (err) {
      setOriginError('Could not originate mission (origination may be disabled)');
    } finally {
      setOriginBusy(false);
    }
  }, [originGoal, originFiles, originVerification, loadMissions]);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadMissions(ctrl.signal);
    const id = window.setInterval(() => {
      const poll = new AbortController();
      void loadMissions(poll.signal);
    }, 15000);
    return () => {
      ctrl.abort();
      window.clearInterval(id);
    };
  }, [loadMissions]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(EMPTY_DETAIL);
      return undefined;
    }
    const ctrl = new AbortController();
    let alive = true;
    const loadDetail = async () => {
      try {
        const data = await fetchJson(`/api/v1/council/missions/${encodeURIComponent(selectedId)}`, ctrl.signal);
        if (alive) setDetail(data);
      } catch (err) {
        if (alive && err?.name !== 'AbortError') setDetail(EMPTY_DETAIL);
      }
    };
    void loadDetail();
    return () => {
      alive = false;
      ctrl.abort();
    };
  }, [selectedId]);

  const report = detail.report || selectedSummary || {};
  const ledger = detail.ledger || {};
  const councilVerdicts = asArray(report.council_summary?.council_verdicts || selectedSummary?.councilVerdicts);
  const files = asArray(report.files || selectedSummary?.filesTouched);
  const blockedAttempts = asArray(ledger.blocked_attempts);
  const verificationCommands = asArray(report.verification_result?.commands || ledger.verification?.commands);
  const modelRouting = report.council_summary?.model_routing || selectedSummary?.modelRouting || {};
  const pendingApprovals = asArray(detail.pendingApprovals || detail.summary?.pendingApprovals || selectedSummary?.pendingApprovals);
  const pendingApproval = pendingApprovals[0] || null;
  const kingDecision = detail.kingDecision || detail.summary?.kingDecision || selectedSummary?.kingDecision || null;
  const approvalNeeded = report.approval_needed ?? selectedSummary?.approvalNeeded;
  const rollbackAvailable = Boolean(report.rollback_available ?? selectedSummary?.rollbackAvailable);
  const rollbackId = report.rollback_id ?? selectedSummary?.rollbackId ?? null;
  const canDecide = Boolean(selectedSummary && !kingDecision && (pendingApproval || approvalNeeded));
  const canRollback = Boolean(selectedSummary && rollbackAvailable && rollbackId && !rollbackBusy);
  const risk = report.risk || selectedSummary?.risk || 'GREEN';
  const verification = deriveVerificationStrength(report, selectedSummary);

  const submitDecision = useCallback(async (approved) => {
    if (!selectedSummary || !canDecide) return;
    setDecisionBusy(true);
    setDecisionError('');
    try {
      const data = await postJson(`/api/v1/council/${approved ? 'approve' : 'reject'}`, {
        missionId: selectedSummary.missionId,
        requestId: pendingApproval?.requestId,
        contractDigest: detail.missionAuthority?.contractDigest,
        reason: approved ? 'Approved from Council dashboard' : 'Rejected from Council dashboard',
      });
      const remainingApprovals = pendingApproval
        ? pendingApprovals.filter((approval) => approval.requestId !== pendingApproval.requestId)
        : pendingApprovals;
      setDetail((current) => ({
        ...current,
        pendingApprovals: remainingApprovals,
        kingDecision: data.decision,
        summary: current.summary ? {
          ...current.summary,
          pendingApprovals: remainingApprovals,
          kingDecision: data.decision,
        } : current.summary,
      }));
      void loadMissions();
    } catch (err) {
      setDecisionError('Decision failed');
    } finally {
      setDecisionBusy(false);
    }
  }, [canDecide, loadMissions, pendingApproval, pendingApprovals, selectedSummary]);

  const submitRollback = useCallback(async () => {
    if (!selectedSummary || !rollbackId || !rollbackAvailable) return;
    const confirmed = window.confirm(
      `Rollback ${selectedSummary.missionId} to snapshot ${String(rollbackId).slice(0, 12)}?`,
    );
    if (!confirmed) return;
    setRollbackBusy(true);
    setRollbackError('');
    try {
      const path = `/api/v1/council/missions/${encodeURIComponent(selectedSummary.missionId)}/rollback`;
      const pending = await postJson(path, { snapshotId: rollbackId });
      if (!pending.approvalToken) throw new Error('missing rollback approval token');
      const restored = await postJson(path, {
        snapshotId: rollbackId,
        approvalToken: pending.approvalToken,
      });
      setDetail((current) => ({
        ...current,
        report: restored.report || current.report,
        summary: current.summary ? {
          ...current.summary,
          status: restored.report?.status || 'rolled_back',
          recommendation: restored.report?.recommendation || 'observe',
          rollbackAvailable: false,
          rollbackId: restored.snapshotId || rollbackId,
        } : current.summary,
      }));
      void loadMissions();
    } catch (err) {
      setRollbackError('Rollback failed');
    } finally {
      setRollbackBusy(false);
    }
  }, [loadMissions, rollbackAvailable, rollbackId, selectedSummary]);

  return (
    <aside className="council-dashboard" aria-label="Council runtime dashboard">
      <div className="council-dashboard__header">
        <div>
          <p className="council-dashboard__eyebrow">Council Runtime</p>
          <h2>King Report</h2>
        </div>
        <button
          type="button"
          className={`council-dashboard__icon-btn${manualRefreshing ? ' is-refreshing' : ''}`}
          onClick={() => {
            setManualRefreshing(true);
            loadMissions().finally(() => setManualRefreshing(false));
          }}
          aria-label="Refresh council reports"
          title="Refresh"
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="council-dashboard__tabs" role="tablist" aria-label="Dashboard views">
        {[
          ['missions', 'Missions'],
          ['proposals', 'Self-Analysis'],
          ['sovereign', 'Sovereign State'],
          ['knowledge', 'Knowledge & Memory'],
          ['policy', 'Policy & Control'],
          ['services', 'Services & Runtime'],
          ['debugger', 'Debugger & Alignment'],
          ['security', 'Security Audit'],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={view === key}
            className={`council-dashboard__tab${view === key ? ' is-active' : ''}`}
            onClick={() => setView(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {view === 'proposals' ? <SelfAnalysisProposals /> : null}
      {view === 'sovereign' ? <SovereignStatePanel /> : null}
      {view === 'knowledge' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <KnowledgeIngestPanel />
          <MemoryOperationsPanel />
        </div>
      ) : null}
      {view === 'policy' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <PolicyEnforcementHUD />
          <SovereigntyControls />
        </div>
      ) : null}
      {view === 'services' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <CouncilServicesPanel />
          <RuntimeSurfaceHUD />
        </div>
      ) : null}
      {view === 'debugger' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <ExecutionDebuggerPanel />
          <AlignmentHUD />
        </div>
      ) : null}
      {view === 'security' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <SecurityAuditPanel />
        </div>
      ) : null}
      {view !== 'missions' ? null : (
      <>
      <form
        className="council-dashboard__originate"
        onSubmit={(event) => {
          event.preventDefault();
          void submitOrigination();
        }}
        aria-label="Originate a council mission"
      >
        <textarea
          className="council-dashboard__origin-goal"
          value={originGoal}
          onChange={(event) => setOriginGoal(event.target.value)}
          placeholder="Mission goal (e.g. add aria-labels to the login form)"
          rows={2}
          aria-label="Mission goal"
        />
        <input
          type="text"
          className="council-dashboard__origin-files"
          value={originFiles}
          onChange={(event) => setOriginFiles(event.target.value)}
          placeholder="Allowed files (comma or newline separated)"
          aria-label="Allowed files"
        />
        <textarea
          className="council-dashboard__origin-verification"
          value={originVerification}
          onChange={(event) => setOriginVerification(event.target.value)}
          placeholder="Verification commands (one per line, e.g. npm test)"
          rows={2}
          aria-label="Verification commands"
        />
        {originError ? <p className="council-dashboard__error">{originError}</p> : null}
        <button type="submit" disabled={originBusy}>
          {originBusy ? 'Sending…' : 'Send to Council'}
        </button>
      </form>

      <div className="council-dashboard__body">
        <div className="council-dashboard__missions" aria-label="Council missions">
          {missions.length === 0 ? (
            <div className="council-dashboard__empty">
              {loading ? 'Syncing council ledger' : error || 'No Council missions recorded'}
            </div>
          ) : (
            missions.map((mission) => (
              <button
                type="button"
                key={mission.missionId}
                className={`council-dashboard__mission ${mission.missionId === selectedSummary?.missionId ? 'is-selected' : ''}`}
                onClick={() => setSelectedId(mission.missionId)}
              >
                <span className={`council-dashboard__risk-dot is-${riskTone(mission.risk)}`} aria-hidden="true" />
                <span className="council-dashboard__mission-main">
                  <span>{mission.mission}</span>
                  <small>{mission.status} · {mission.recommendation}</small>
                </span>
              </button>
            ))
          )}
        </div>

        {selectedSummary ? (
          <section
            key={selectedSummary.missionId}
            className="council-dashboard__detail"
            aria-label="Selected King Report"
          >
            <div className="council-dashboard__mission-title">
              <span className={`council-dashboard__badge is-${riskTone(risk)}`}>{risk}</span>
              <strong>{report.mission || selectedSummary.mission}</strong>
            </div>

            <div className="council-dashboard__grid" aria-label="Mission state">
              <span><b>Status</b>{titleCase(report.status || selectedSummary.status)}</span>
              <span><b>Recommendation</b>{titleCase(report.recommendation || selectedSummary.recommendation)}</span>
              <span><b>Approval</b>{approvalNeeded ? 'Needed' : 'Not needed'}</span>
              <span><b>Recovery</b>{rollbackAvailable ? 'Ready' : report.status === 'rolled_back' ? 'Restored' : 'None'}</span>
            </div>

            <div className="council-dashboard__section council-dashboard__decision">
              <h3><ShieldCheck size={14} aria-hidden="true" /> King Decision</h3>
              <strong>
                {kingDecision
                  ? (kingDecision.approved ? 'Approved by King' : 'Rejected by King')
                  : pendingApproval ? 'Pending worker approval' : approvalNeeded ? 'Awaiting decision' : 'Observe only'}
              </strong>
              {pendingApproval ? (
                <p>{pendingApproval.action || 'approval'} · {pendingApproval.reason || 'No reason recorded'}</p>
              ) : null}
              {verification?.warning ? (
                <p className="council-dashboard__caution" role="alert">
                  <AlertTriangle size={13} aria-hidden="true" /> {verification.warning}
                </p>
              ) : null}
              {decisionError ? <p className="council-dashboard__error">{decisionError}</p> : null}
              {canDecide ? (
                <div className="council-dashboard__decision-actions">
                  <button
                    type="button"
                    onClick={() => submitDecision(true)}
                    disabled={decisionBusy}
                    aria-label="Approve Council mission"
                  >
                    <ShieldCheck size={14} aria-hidden="true" />
                    Approve
                  </button>
                  <button
                    type="button"
                    className="is-reject"
                    onClick={() => submitDecision(false)}
                    disabled={decisionBusy}
                    aria-label="Reject Council mission"
                  >
                    <AlertTriangle size={14} aria-hidden="true" />
                    Reject
                  </button>
                </div>
              ) : null}
            </div>

            {rollbackId ? (
              <div className="council-dashboard__section council-dashboard__recovery">
                <h3><RotateCcw size={14} aria-hidden="true" /> Recovery</h3>
                <span className="council-dashboard__snapshot">{String(rollbackId).slice(0, 12)}</span>
                {rollbackError ? <p className="council-dashboard__error">{rollbackError}</p> : null}
                {rollbackAvailable ? (
                  <button
                    type="button"
                    onClick={() => submitRollback()}
                    disabled={!canRollback}
                    aria-label="Rollback Council mission"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Rollback
                  </button>
                ) : null}
              </div>
            ) : null}

            <div className="council-dashboard__section">
              <h3><ShieldCheck size={14} aria-hidden="true" /> Verdicts</h3>
              <div className="council-dashboard__verdicts">
                {councilVerdicts.length ? councilVerdicts.map((verdict) => (
                  <span key={`${verdict.queen}-${verdict.verdict}`} className={`council-dashboard__verdict is-${verdictTone(verdict.verdict)}`}>
                    {titleCase(verdict.queen)}: {titleCase(verdict.verdict)}
                  </span>
                )) : <span className="council-dashboard__muted">No verdicts</span>}
              </div>
            </div>

            <div className="council-dashboard__section">
              <h3><FileText size={14} aria-hidden="true" /> Files</h3>
              <div className="council-dashboard__mono-list">
                {files.length ? files.slice(0, 4).map((file) => <span key={file}>{file}</span>) : <span>No files touched</span>}
              </div>
            </div>

            <div className="council-dashboard__section council-dashboard__split">
              <div>
                <h3><AlertTriangle size={14} aria-hidden="true" /> Blocks</h3>
                <strong>{blockedAttempts.length || selectedSummary.blockedAttempts || 0}</strong>
              </div>
              <div>
                <h3><ShieldCheck size={14} aria-hidden="true" /> Verify</h3>
                {verification ? (
                  <strong
                    className={`council-dashboard__badge is-${verification.tone}`}
                    style={{ opacity: verification.intensity }}
                    title={verification.warning || `Verification strength: ${verification.level}`}
                  >
                    {titleCase(verification.level)}
                  </strong>
                ) : (
                  <strong>
                    {verificationCommands.length
                      ? verificationCommands.every((cmd) => cmd.returncode === 0) ? 'Passed' : 'Failed'
                      : 'None'}
                  </strong>
                )}
              </div>
            </div>

            <div className="council-dashboard__section">
              <h3><Cloud size={14} aria-hidden="true" /> Model Route</h3>
              <div className="council-dashboard__route">
                <span>{modelRouting.provider || 'local'}</span>
                <span>{modelRouting.used_cloud ? 'cloud' : 'local'}</span>
                <span>{modelRouting.fallback_used ? 'fallback' : 'primary'}</span>
              </div>
            </div>
          </section>
        ) : null}
      </div>
      </>
      )}
    </aside>
  );
}
