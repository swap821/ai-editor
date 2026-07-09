import { useCallback, useEffect, useState } from 'react';
import { Activity, Plus, Trash2, Zap } from 'lucide-react';
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

async function deleteJson(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export default function RuntimeSurfaceHUD() {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [emitPayload, setEmitPayload] = useState('{"type": "system_ping", "data": "test"}');
  const [emitBusy, setEmitBusy] = useState(false);
  const [emitError, setEmitError] = useState('');

  const [sweepBusy, setSweepBusy] = useState(false);

  const loadSurface = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/runtime/surface', signal);
      setSignals(asArray(data.signals));
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Runtime surface offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadSurface(ctrl.signal);
    return () => ctrl.abort();
  }, [loadSurface]);

  const handleEmit = async (e) => {
    e.preventDefault();
    if (!emitPayload.trim()) return;
    setEmitBusy(true);
    setEmitError('');
    try {
      let parsed;
      try {
        parsed = JSON.parse(emitPayload);
      } catch {
        throw new Error('Payload must be valid JSON');
      }
      await postJson('/api/v1/runtime/surface/emit', { payload: parsed });
      setEmitPayload('');
      void loadSurface();
    } catch (err) {
      setEmitError(err.message);
    } finally {
      setEmitBusy(false);
    }
  };

  const handleSweep = async () => {
    if (!window.confirm('Sweep all signals from the surface?')) return;
    setSweepBusy(true);
    try {
      await postJson('/api/v1/runtime/surface/sweep');
      void loadSurface();
    } catch (err) {
      alert('Sweep failed');
    } finally {
      setSweepBusy(false);
    }
  };

  const handleDelete = async (signalId) => {
    try {
      await deleteJson(`/api/v1/runtime/surface/${encodeURIComponent(signalId)}`);
      void loadSurface();
    } catch (err) {
      alert('Failed to delete signal');
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Runtime Surface">
      <div className="council-dashboard__detail">

        <section className="council-dashboard__section">
          <h3>
            <Activity size={14} aria-hidden="true" /> Floating Signals
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Event bus signals floating on the runtime surface.
          </p>
          
          <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', marginBottom: '12px' }}>
            <button 
              type="button" 
              className="is-reject"
              onClick={handleSweep}
              disabled={sweepBusy || signals.length === 0}
            >
              <Zap size={14} /> Sweep Surface
            </button>
          </div>

          {loading ? (
            <p className="council-dashboard__muted">Scanning surface...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : signals.length === 0 ? (
            <p className="council-dashboard__muted">Surface is clean.</p>
          ) : (
            signals.map((sig) => (
              <div key={sig.id} className="council-dashboard__route" style={{ display: 'block', padding: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <strong>{sig.type || 'unknown'}</strong>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                     <span className="council-dashboard__muted" style={{ fontSize: '10px' }}>{sig.id.substring(0,8)}</span>
                     <button type="button" style={{ background: 'none', border: 'none', padding: 0, color: 'var(--danger)' }} onClick={() => handleDelete(sig.id)}>
                       <Trash2 size={12} />
                     </button>
                  </div>
                </div>
                <pre style={{ margin: 0, fontSize: '10px', overflowX: 'auto', background: 'rgba(0,0,0,0.2)', padding: '4px', borderRadius: '4px' }}>
                  {JSON.stringify(sig.payload, null, 2)}
                </pre>
              </div>
            ))
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <Plus size={14} aria-hidden="true" /> Emit Signal
          </h3>
          <form className="council-dashboard__originate" onSubmit={handleEmit}>
            <textarea
              className="council-dashboard__origin-goal"
              value={emitPayload}
              onChange={(e) => setEmitPayload(e.target.value)}
              placeholder='{"type": "event", "data": 123}'
              rows={4}
              style={{ fontFamily: 'monospace' }}
              required
            />
            {emitError ? <p className="council-dashboard__error">{emitError}</p> : null}
            <button type="submit" disabled={emitBusy}>
              {emitBusy ? 'Emitting...' : 'Emit to Surface'}
            </button>
          </form>
        </section>

      </div>
    </div>
  );
}
