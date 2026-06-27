import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Cloud, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';
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

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, { signal, headers: API_HEADERS });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body),
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
  const canDecide = Boolean(selectedSummary && !kingDecision && (pendingApproval || approvalNeeded));
  const risk = report.risk || selectedSummary?.risk || 'GREEN';

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
              <span><b>Rollback</b>{report.rollback_available ?? selectedSummary.rollbackAvailable ? (report.rollback_id || 'Available') : 'None'}</span>
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
                <strong>
                  {verificationCommands.length
                    ? verificationCommands.every((cmd) => cmd.returncode === 0) ? 'Passed' : 'Failed'
                    : 'None'}
                </strong>
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
