import { useCallback, useEffect, useState } from 'react';
import { Scale, BookOpen, Hand, Play, Pause, HandMetal, AlertTriangle } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, body = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function invalidResponse(message) {
  const error = new Error(message);
  error.code = 'INVALID_RESPONSE';
  return error;
}

function parsePolicyPayload(data) {
  if (!data || typeof data !== 'object' || !Array.isArray(data.policies)) {
    throw invalidResponse('Policy chain response did not contain a policies array');
  }
  return data.policies.map((policy) => {
    if (!policy || typeof policy !== 'object'
      || typeof policy.policy_id !== 'string' || !policy.policy_id.trim()
      || typeof policy.constraint !== 'string' || !policy.constraint.trim()
      || typeof policy.status !== 'string' || !policy.status.trim()) {
      throw invalidResponse('Policy chain response contained an invalid policy record');
    }
    return {
      id: policy.policy_id,
      text: policy.constraint,
      status: policy.status,
      version: policy.version,
      proposedBy: policy.proposed_by,
      enactedAt: policy.enacted_at,
    };
  });
}

export default function PolicyEnforcementHUD() {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyAction, setBusyAction] = useState(null);
  const [actionError, setActionError] = useState('');
  const [voteQueen, setVoteQueen] = useState('');
  const [voteReason, setVoteReason] = useState('');
  const [requiredApprovals, setRequiredApprovals] = useState('3');
  
  const [newPolicyText, setNewPolicyText] = useState('');
  const [proposeBusy, setProposeBusy] = useState(false);
  const [proposeError, setProposeError] = useState('');

  const loadChain = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/policy/chain', signal);
      setPolicies(parsePolicyPayload(data));
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setError(err?.code === 'INVALID_RESPONSE' ? 'Policy chain unavailable' : 'Policy chain offline');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadChain(ctrl.signal);
    return () => ctrl.abort();
  }, [loadChain]);

  const handleAction = async (policyId, action) => {
    let body = {};
    if (action === 'vote') {
      if (!voteQueen.trim()) {
        setActionError('Name the Council queen whose vote is being recorded.');
        return;
      }
      body = { queen: voteQueen.trim(), approve: true, reason: voteReason.trim() };
    } else if (action === 'enact') {
      const approvals = Number(requiredApprovals);
      if (!Number.isSafeInteger(approvals) || approvals < 1) {
        setActionError('Required approvals must be a positive whole number.');
        return;
      }
      body = { requiredApprovals: approvals };
    }
    setActionError('');
    setBusyAction(`${policyId}-${action}`);
    try {
      if (action === 'vote' && !window.confirm(`Vote to approve policy ${policyId}?`)) return;
      await postJson(`/api/v1/policy/${encodeURIComponent(policyId)}/${action}`, body);
      void loadChain();
    } catch (err) {
      alert(`Could not ${action} policy`);
    } finally {
      setBusyAction(null);
    }
  };

  const handlePropose = async (e) => {
    e.preventDefault();
    if (!newPolicyText.trim()) return;
    setProposeBusy(true);
    setProposeError('');
    try {
      await postJson('/api/v1/policy/propose', { constraint: newPolicyText.trim() });
      setNewPolicyText('');
      void loadChain();
    } catch (err) {
      setProposeError('Proposal failed: ' + err.message);
    } finally {
      setProposeBusy(false);
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Policy Enforcement">
      <div className="council-dashboard__detail">
        
        <section className="council-dashboard__section">
          <h3>
            <Scale size={14} aria-hidden="true" /> Propose New Constraint
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Inject a hard constraint into the AI-OS policy chain. Must be voted on by the Council to be enacted.
          </p>
          <form className="council-dashboard__originate" onSubmit={handlePropose}>
            <textarea
              className="council-dashboard__origin-goal"
              value={newPolicyText}
              onChange={(e) => setNewPolicyText(e.target.value)}
              placeholder="e.g. 'Never write to the C:\Windows directory'"
              rows={2}
              required
            />
            {proposeError ? <p className="council-dashboard__error">{proposeError}</p> : null}
            <button type="submit" disabled={proposeBusy}>
              {proposeBusy ? 'Proposing...' : 'Submit Proposal'}
            </button>
          </form>
        </section>

        <section className="council-dashboard__section">
          <h3>
            <BookOpen size={14} aria-hidden="true" /> Active Policy Chain
          </h3>
          {policies.some((policy) => policy.status === 'proposed') && (
            <div className="council-dashboard__originate" style={{ marginBottom: '12px' }}>
              <label>
                Council queen for vote
                <input aria-label="Policy voting queen" value={voteQueen} onChange={(e) => setVoteQueen(e.target.value)} placeholder="e.g. planner" />
              </label>
              <label>
                Vote reason
                <input aria-label="Policy vote reason" value={voteReason} onChange={(e) => setVoteReason(e.target.value)} placeholder="Why this vote is being recorded" />
              </label>
              <label>
                Required approvals to enact
                <input aria-label="Required policy approvals" type="number" min="1" step="1" value={requiredApprovals} onChange={(e) => setRequiredApprovals(e.target.value)} />
              </label>
            </div>
          )}
          {actionError ? <p className="council-dashboard__error">{actionError}</p> : null}
          {loading ? (
            <p className="council-dashboard__muted">Syncing ledger...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : policies.length === 0 ? (
            <p className="council-dashboard__muted">No policies active in the chain.</p>
          ) : (
            policies.map((p) => {
              const isPending = p.status === 'proposed';
              const isSuspended = p.status === 'suspended';
              const isEnacted = p.status === 'enacted';
              
              return (
                <div key={p.id} className="council-dashboard__section" style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '4px', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <strong>{p.id.substring(0, 8)}</strong>
                    <span className={`council-dashboard__badge is-${isEnacted ? 'ok' : isPending ? 'warn' : 'danger'}`}>
                      {p.status}
                    </span>
                  </div>
                  <p style={{ margin: '0 0 12px 0', fontSize: '0.9em' }}>{p.text}</p>
                  
                  <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
                    {isPending && (
                      <button 
                        type="button" 
                        disabled={busyAction === `${p.id}-vote` || !voteQueen.trim()}
                        onClick={() => handleAction(p.id, 'vote')}
                      >
                        <Hand size={14} /> Vote Approve
                      </button>
                    )}
                    {(isPending || isSuspended) && (
                      <button 
                        type="button" 
                        disabled={busyAction === `${p.id}-enact` || !Number.isSafeInteger(Number(requiredApprovals)) || Number(requiredApprovals) < 1}
                        onClick={() => handleAction(p.id, 'enact')}
                      >
                        <Play size={14} /> Enact
                      </button>
                    )}
                    {isEnacted && (
                      <button 
                        type="button" 
                        className="is-reject"
                        disabled={busyAction === `${p.id}-suspend`}
                        onClick={() => handleAction(p.id, 'suspend')}
                      >
                        <Pause size={14} /> Suspend
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </section>

      </div>
    </div>
  );
}
