import { useState, useEffect, useCallback } from 'react';
import DiffView from './DiffView';
import { ErrorBoundary } from './ErrorBoundary';
import { API_BASE, API_HEADERS } from '../config';

// The agent's proposer identity — the backend refuses an apply approved by it
// (no self-approval, §6.3). Mirror it here so the UI never sends a doomed request.
const SELF_PROPOSER = 'self_analysis_agent';

/* Zone badge — RED (frozen core, apply blocked) vs YELLOW (ordinary aios/). */
function ZoneBadge({ zone }) {
  const red = zone === 'RED';
  return (
    <span
      data-testid="zone-badge"
      style={{
        fontSize: 9, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase',
        padding: '2px 7px', borderRadius: 5,
        color: red ? '#f87171' : '#fbbf24',
        background: red ? 'rgba(248,113,113,0.12)' : 'rgba(251,191,36,0.12)',
        border: `1px solid ${red ? 'rgba(248,113,113,0.30)' : 'rgba(251,191,36,0.28)'}`,
      }}
    >
      {zone || 'YELLOW'}
    </span>
  );
}

/* The applied/rolled_back/refused verdict returned by the apply endpoint. */
function ResultBanner({ result }) {
  if (!result) return null;
  const palette = {
    applied: '#22c55e', rolled_back: '#fbbf24', refused: '#f87171', error: '#f87171',
  };
  const color = palette[result.status] || 'var(--text-2)';
  return (
    <div
      data-testid="apply-result"
      style={{
        marginTop: 8, padding: '7px 10px', borderRadius: 8, fontSize: 11.5,
        color, background: 'rgba(255,255,255,0.03)', border: `1px solid ${color}33`,
      }}
    >
      <strong style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}>{result.status}</strong>
      {result.reason ? ` — ${result.reason}` : ''}
      {result.verify ? <div style={{ marginTop: 4, color: 'var(--text-3)' }}>verify: {result.verify}</div> : null}
    </div>
  );
}

/* Review/approve panel for Self-Analysis T2 proposals (T3b). Lists 'proposed'
   rows and applies/rejects them via the merged T3a endpoints — the whole
   self-improvement loop, visible and clickable (no curl). */
export default function ProposalsPanel() {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [approvedBy, setApprovedBy] = useState('operator');
  const [results, setResults] = useState({});   // id -> verdict
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/self-analysis/proposals?status=proposed`, { headers: API_HEADERS });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setProposals(data.proposals || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Mirror the backend no-self-approval guard so a doomed request is never sent.
  const approverInvalid = !approvedBy.trim() || approvedBy.trim() === SELF_PROPOSER;

  const handleApprove = async (id) => {
    if (approverInvalid) return;
    setBusyId(id);
    try {
      const res = await fetch(`${API_BASE}/api/v1/self-analysis/proposals/${id}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ approvedBy: approvedBy.trim() }),
      });
      const data = await res.json();
      setResults(prev => ({ ...prev, [id]: data }));
      await load();
    } catch (e) {
      setResults(prev => ({ ...prev, [id]: { status: 'error', reason: e.message } }));
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (id) => {
    setBusyId(id);
    try {
      await fetch(`${API_BASE}/api/v1/self-analysis/proposals/${id}/reject`, { method: 'POST', headers: API_HEADERS });
      await load();
    } catch (e) {
      setResults(prev => ({ ...prev, [id]: { status: 'error', reason: e.message } }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <ErrorBoundary name="ProposalsPanel">
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* header: title + the human approver id */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>
          Self-Analysis proposals
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
          review a fix diff, then Approve (apply + verify + auto-rollback) or Reject
        </span>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-3)' }}>
          approved by
          <input
            aria-label="approved by"
            value={approvedBy}
            onChange={e => setApprovedBy(e.target.value)}
            style={{
              width: 130, padding: '4px 8px', borderRadius: 6, fontSize: 11.5,
              background: 'var(--surface-3)', color: 'var(--text-1)',
              border: `1px solid ${approverInvalid ? 'rgba(248,113,113,0.5)' : 'var(--border)'}`,
              outline: 'none',
            }}
          />
        </label>
        <button
          onClick={load}
          style={{
            fontSize: 11, padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
            background: 'var(--surface-3)', color: 'var(--text-2)', border: '1px solid var(--border)',
          }}
        >
          Refresh
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
        {loading && (
          <div data-testid="proposals-loading" style={{ color: 'var(--text-3)', fontSize: 12, padding: 12 }}>
            Loading proposals…
          </div>
        )}
        {error && !loading && (
          <div data-testid="proposals-error" style={{ color: '#f87171', fontSize: 12, padding: 12 }}>
            Failed to load proposals: {error}
          </div>
        )}
        {!loading && !error && proposals.length === 0 && (
          <div data-testid="proposals-empty" style={{ color: 'var(--text-3)', fontSize: 12, padding: 12 }}>
            No open proposals. Run <code>propose_fixes</code> to generate some.
          </div>
        )}

        {!loading && !error && proposals.map(p => {
          const red = p.proposed_zone === 'RED';
          return (
            <div
              key={p.id}
              data-testid={`proposal-${p.id}`}
              style={{
                marginBottom: 12, padding: 12, borderRadius: 10,
                background: 'var(--surface-2)', border: '1px solid var(--border)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <ZoneBadge zone={p.proposed_zone} />
                <code style={{ fontSize: 12, color: 'var(--text-1)', fontWeight: 600 }}>{p.target_path}</code>
                <span style={{
                  fontSize: 10, fontWeight: 700, color: 'var(--text-3)',
                  background: 'var(--surface-3)', borderRadius: 4, padding: '1px 6px',
                }}>{p.finding_type}</span>
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-2)', marginBottom: 8 }}>{p.evidence}</div>

              <DiffView diff={p.proposed_diff || ''} />

              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {red ? (
                  <button
                    disabled
                    title="The frozen security core is review-only (T4)."
                    style={{
                      fontSize: 12, fontWeight: 600, padding: '7px 14px', borderRadius: 8,
                      border: '1px solid rgba(248,113,113,0.3)', background: 'rgba(248,113,113,0.08)',
                      color: '#f87171', cursor: 'not-allowed',
                    }}
                  >
                    RED — apply blocked (T4)
                  </button>
                ) : (
                  <button
                    onClick={() => handleApprove(p.id)}
                    disabled={approverInvalid || busyId === p.id}
                    style={{
                      fontSize: 12, fontWeight: 700, padding: '7px 16px', borderRadius: 8, border: 'none',
                      background: (approverInvalid || busyId === p.id) ? 'var(--surface-3)' : 'linear-gradient(135deg,#22c55e,#16a34a)',
                      color: (approverInvalid || busyId === p.id) ? 'var(--text-3)' : '#fff',
                      cursor: (approverInvalid || busyId === p.id) ? 'not-allowed' : 'pointer',
                    }}
                  >
                    Approve &amp; apply
                  </button>
                )}
                <button
                  onClick={() => handleReject(p.id)}
                  disabled={busyId === p.id}
                  style={{
                    fontSize: 12, fontWeight: 600, padding: '7px 14px', borderRadius: 8,
                    border: '1px solid rgba(248,113,113,0.22)', background: 'rgba(248,113,113,0.08)',
                    color: '#f87171', cursor: busyId === p.id ? 'not-allowed' : 'pointer',
                  }}
                >
                  Reject
                </button>
                {approverInvalid && !red && (
                  <span style={{ fontSize: 10.5, color: '#f87171' }}>
                    enter a human approver (not the agent)
                  </span>
                )}
              </div>

              <ResultBanner result={results[p.id]} />
            </div>
          );
        })}
      </div>
    </div>
    </ErrorBoundary>
  );
}
