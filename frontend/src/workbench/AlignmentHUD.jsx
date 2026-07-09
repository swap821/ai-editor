import { useCallback, useEffect, useState } from 'react';
import { Target, RefreshCcw } from 'lucide-react';
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

export default function AlignmentHUD() {
  const [alignmentState, setAlignmentState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncError, setSyncError] = useState('');
  const [syncMessage, setSyncMessage] = useState('');

  const loadAlignment = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/conversation/alignment', signal);
      setAlignmentState(data);
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Alignment data offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadAlignment(ctrl.signal);
    return () => ctrl.abort();
  }, [loadAlignment]);

  const handleSync = async () => {
    setSyncBusy(true);
    setSyncError('');
    setSyncMessage('');
    try {
      const res = await postJson('/api/v1/conversation/alignment/sync');
      setSyncMessage(res.message || 'Sync complete');
      void loadAlignment();
    } catch (err) {
      setSyncError('Sync failed: ' + err.message);
    } finally {
      setSyncBusy(false);
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Conversation Alignment">
      <div className="council-dashboard__detail">
        
        <section className="council-dashboard__section">
          <h3>
            <Target size={14} aria-hidden="true" /> Alignment Posture
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Current conversation alignment frame and drift status.
          </p>
          {loading ? (
            <p className="council-dashboard__muted">Loading alignment...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : !alignmentState ? (
            <p className="council-dashboard__muted">No alignment data.</p>
          ) : (
            <div className="council-dashboard__verdicts" style={{ marginTop: '12px' }}>
              <pre style={{ margin: 0, fontSize: '10px', overflowX: 'auto' }}>
                {JSON.stringify(alignmentState, null, 2)}
              </pre>
            </div>
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <RefreshCcw size={14} aria-hidden="true" /> Force Sync
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Re-synchronize alignment model with the current conversation context.
          </p>
          <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start' }}>
            <button
              type="button"
              onClick={handleSync}
              disabled={syncBusy}
            >
              <RefreshCcw size={14} /> {syncBusy ? 'Syncing...' : 'Sync Alignment'}
            </button>
          </div>
          {syncError && <p className="council-dashboard__error" style={{ marginTop: '8px' }}>{syncError}</p>}
          {syncMessage && <p className="council-dashboard__badge is-ok" style={{ display: 'inline-block', marginTop: '8px' }}>{syncMessage}</p>}
        </section>

      </div>
    </div>
  );
}
