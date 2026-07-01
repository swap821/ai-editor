import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Cloud, FileText, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';
import { ensureSession } from '../superbrain/lib/sessionId';
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
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify({ ...sessionBody, ...body }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export default function CouncilDashboard() {
  const [missions, setMissions] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(EMPTY_DETAIL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState('');
  const [rollbackBusy, setRollbackBusy] = useState(false);
  const [rollbackError, setRollbackError] = useState('');
  const [originGoal, setOriginGoal] = useState('');
  const [originFiles, setOriginFiles] = useState('');
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
    if (!goal || allowedFiles.length === 0) {
      setOriginError('Goal and at least one allowed file are required');
      return;
    }
    setOriginBusy(true);
    setOriginError('');
    try {
      await postJson('/api/v1/council/missions', { goal, allowedFiles });
      setOriginGoal('');
      setOriginFiles('');
      void loadMissions();
    } catch (err) {
      setOriginError('Could not originate mission (origination may be disabled)');
    } finally {
      setOriginBusy(false);
    }
  }, [originGoal, originFiles, loadMissions]);

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
          className="council-dashboard__icon-btn"
          onClick={() => loadMissions()}
          aria-label="Refresh council reports"
          title="Refresh"
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>

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
          <section className="council-dashboard__detail" aria-label="Selected King Report">
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
    </aside>
  );
}
