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

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export default function PolicyEnforcementHUD() {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyAction, setBusyAction] = useState(null);
  
  const [newPolicyText, setNewPolicyText] = useState('');
  const [proposeBusy, setProposeBusy] = useState(false);
  const [proposeError, setProposeError] = useState('');

  const loadChain = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/policy/chain', signal);
      setPolicies(asArray(data.policies));
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Policy chain offline');
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
    setBusyAction(`${policyId}-${action}`);
    try {
      if (action === 'vote' && !window.confirm(`Vote to approve policy ${policyId}?`)) return;
      await postJson(`/api/v1/policy/${encodeURIComponent(policyId)}/${action}`);
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
      await postJson('/api/v1/policy/propose', { policyText: newPolicyText });
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
                        disabled={busyAction === `${p.id}-vote`}
                        onClick={() => handleAction(p.id, 'vote')}
                      >
                        <Hand size={14} /> Vote Approve
                      </button>
                    )}
                    {(isPending || isSuspended) && (
                      <button 
                        type="button" 
                        disabled={busyAction === `${p.id}-enact`}
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
