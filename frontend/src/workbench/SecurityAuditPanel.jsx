import { useCallback, useEffect, useState } from 'react';
import { Shield, ShieldAlert, Key, Trash2 } from 'lucide-react';
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

export default function SecurityAuditPanel() {
  const [auditLog, setAuditLog] = useState([]);
  const [chainValid, setChainValid] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [busyAction, setBusyAction] = useState(null);

  const loadAudit = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      // Real Ed25519-signed hash-chained ledger (aios/security/audit_logger.py).
      const data = await fetchJson('/api/v1/security/audit', signal);
      setAuditLog(asArray(data.entries));
      setChainValid(data.chainValid);
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Security audit offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadAudit(ctrl.signal);
    return () => ctrl.abort();
  }, [loadAudit]);

  const handleAction = async (actionPath, actionId, body = {}) => {
    if (!window.confirm(`Are you sure you want to ${actionId}? This action is real and audited.`)) return;
    setBusyAction(actionId);
    try {
      await postJson(actionPath, body);
      alert(`${actionId} complete.`);
      void loadAudit();
    } catch (err) {
      alert(`${actionId} failed: ${err.message}`);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Security Audit">
      <div className="council-dashboard__detail">
        
        <section className="council-dashboard__section">
          <h3>
            <ShieldAlert size={14} aria-hidden="true" /> Security Operations
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Critical enclave security controls.
          </p>
          <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
            <button
              type="button"
              className="is-reject"
              onClick={() => handleAction('/api/v1/security/sandbox/clear', 'Clear Sandbox', { confirm: true })}
              disabled={busyAction !== null}
            >
              <Trash2 size={14} /> Clear Sandbox
            </button>
            <button
              type="button"
              className="is-reject"
              onClick={() => handleAction('/api/v1/security/tokens/rotate', 'Rotate Tokens')}
              disabled={busyAction !== null}
            >
              <Key size={14} /> Rotate Tokens
            </button>
          </div>
        </section>

        <section className="council-dashboard__section">
          <h3>
            <Shield size={14} aria-hidden="true" /> Audit Log
          </h3>
          {chainValid !== null && (
            <p className={chainValid ? 'council-dashboard__badge is-ok' : 'council-dashboard__error'} style={{ display: 'inline-block', marginBottom: '8px' }}>
              Hash chain: {chainValid ? 'valid' : 'BROKEN'}
            </p>
          )}
          {loading ? (
            <p className="council-dashboard__muted">Loading audit log...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : auditLog.length === 0 ? (
            <p className="council-dashboard__muted">No audit events found.</p>
          ) : (
            auditLog.map((entry) => (
              <div key={entry.entryId} className="council-dashboard__route" style={{ display: 'block', padding: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <strong>{entry.actor} — {entry.zone}</strong>
                  <span className="council-dashboard__muted" style={{ fontSize: '10px' }}>
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                </div>
                <div className="council-dashboard__muted" style={{ fontSize: '11px' }}>
                  {entry.payload}
                </div>
              </div>
            ))
          )}
        </section>

      </div>
    </div>
  );
}
