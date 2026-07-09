import { useCallback, useEffect, useState } from 'react';
import { Bug, Play, StepForward } from 'lucide-react';
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

export default function ExecutionDebuggerPanel() {
  const [debuggerState, setDebuggerState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyAction, setBusyAction] = useState(null);
  
  const [stepMissionId, setStepMissionId] = useState('');

  const loadState = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/execution/debugger/state', signal);
      setDebuggerState(data);
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Debugger offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadState(ctrl.signal);
    return () => ctrl.abort();
  }, [loadState]);

  const handleAction = async (action, missionId) => {
    if (!missionId) return;
    setBusyAction(`${action}-${missionId}`);
    try {
      await postJson(`/api/v1/execution/debugger/${action}`, { missionId });
      void loadState();
      setStepMissionId('');
    } catch (err) {
      alert(`Could not ${action} execution: ${err.message}`);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Execution Debugger">
      <div className="council-dashboard__detail">
        
        <section className="council-dashboard__section">
          <h3>
            <Bug size={14} aria-hidden="true" /> Global Debugger State
          </h3>
          {loading ? (
            <p className="council-dashboard__muted">Loading state...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : !debuggerState ? (
            <p className="council-dashboard__muted">No state available.</p>
          ) : (
            <div className="council-dashboard__verdicts" style={{ marginTop: '12px' }}>
              <pre style={{ margin: 0, fontSize: '10px', overflowX: 'auto' }}>
                {JSON.stringify(debuggerState, null, 2)}
              </pre>
            </div>
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <StepForward size={14} aria-hidden="true" /> Step / Resume
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Control execution of a paused mission.
          </p>
          <div className="council-dashboard__originate">
            <input
              type="text"
              className="council-dashboard__origin-files"
              style={{ marginBottom: '4px' }}
              value={stepMissionId}
              onChange={(e) => setStepMissionId(e.target.value)}
              placeholder="Mission ID"
            />
            <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
              <button
                type="button"
                onClick={() => handleAction('step', stepMissionId)}
                disabled={!stepMissionId.trim() || busyAction !== null}
              >
                <StepForward size={14} /> Step
              </button>
              <button
                type="button"
                onClick={() => handleAction('resume', stepMissionId)}
                disabled={!stepMissionId.trim() || busyAction !== null}
              >
                <Play size={14} /> Resume
              </button>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
