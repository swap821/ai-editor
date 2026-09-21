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

const SIGNAL_TYPES = ['file-lock', 'worker-active', 'attention-needed', 'progress-update'];

function invalidResponse(message) {
  const error = new Error(message);
  error.code = 'INVALID_RESPONSE';
  return error;
}

function parseSurfacePayload(data) {
  if (!data || typeof data !== 'object' || !Array.isArray(data.signals)) {
    throw invalidResponse('Runtime surface response did not contain a signals array');
  }
  return data.signals.map((signal) => {
    if (!signal || typeof signal !== 'object'
      || !Number.isSafeInteger(signal.signal_id)
      || typeof signal.stype !== 'string' || !SIGNAL_TYPES.includes(signal.stype)
      || typeof signal.resource !== 'string' || !signal.resource.trim()
      || typeof signal.worker_id !== 'string' || !signal.worker_id.trim()
      || !Number.isSafeInteger(signal.ttl_seconds) || signal.ttl_seconds < 1
      || !signal.payload || typeof signal.payload !== 'object' || Array.isArray(signal.payload)) {
      throw invalidResponse('Runtime surface response contained an invalid signal');
    }
    return {
      id: signal.signal_id,
      type: signal.stype,
      resource: signal.resource,
      workerId: signal.worker_id,
      ttlSeconds: signal.ttl_seconds,
      payload: signal.payload,
      createdAt: signal.created_at,
    };
  });
}

export default function RuntimeSurfaceHUD() {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [emitType, setEmitType] = useState('');
  const [emitResource, setEmitResource] = useState('');
  const [emitWorker, setEmitWorker] = useState('');
  const [emitTtl, setEmitTtl] = useState('30');
  const [emitPayload, setEmitPayload] = useState('{"type": "system_ping", "data": "test"}');
  const [emitBusy, setEmitBusy] = useState(false);
  const [emitError, setEmitError] = useState('');

  const [sweepBusy, setSweepBusy] = useState(false);

  const loadSurface = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/runtime/surface', signal);
      setSignals(parseSurfacePayload(data));
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setError(err?.code === 'INVALID_RESPONSE' ? 'Runtime surface unavailable' : 'Runtime surface offline');
      }
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
    const ttlSeconds = Number(emitTtl);
    if (!emitType || !emitResource.trim() || !emitWorker.trim() || !Number.isSafeInteger(ttlSeconds) || ttlSeconds < 1 || !emitPayload.trim()) return;
    setEmitBusy(true);
    setEmitError('');
    try {
      let parsed;
      try {
        parsed = JSON.parse(emitPayload);
      } catch {
        throw new Error('Payload must be valid JSON');
      }
      await postJson('/api/v1/runtime/surface/emit', {
        stype: emitType,
        resource: emitResource.trim(),
        workerId: emitWorker.trim(),
        ttlSeconds,
        payload: parsed,
      });
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
                     <span className="council-dashboard__muted" style={{ fontSize: '10px' }}>{String(sig.id).substring(0,8)}</span>
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
            <label>
              Signal type
              <select aria-label="Signal type" value={emitType} onChange={(e) => setEmitType(e.target.value)} required>
                <option value="">Choose a signal type</option>
                {SIGNAL_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label>
              Resource
              <input aria-label="Signal resource" value={emitResource} onChange={(e) => setEmitResource(e.target.value)} required placeholder="Enrolled resource or mission" />
            </label>
            <label>
              Worker ID
              <input aria-label="Signal worker" value={emitWorker} onChange={(e) => setEmitWorker(e.target.value)} required placeholder="Bound worker identity" />
            </label>
            <label>
              TTL seconds
              <input aria-label="Signal TTL seconds" type="number" min="1" step="1" value={emitTtl} onChange={(e) => setEmitTtl(e.target.value)} required />
            </label>
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
            <button type="submit" disabled={emitBusy || !emitType || !emitResource.trim() || !emitWorker.trim() || !Number.isSafeInteger(Number(emitTtl)) || Number(emitTtl) < 1}>
              {emitBusy ? 'Emitting...' : 'Emit to Surface'}
            </button>
          </form>
        </section>

      </div>
    </div>
  );
}
