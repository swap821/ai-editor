import { useState } from 'react';
import { Power, RotateCcw, Box, Activity, Droplet, Wind, Zap } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

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

export default function SovereigntyControls() {
  const [busyAction, setBusyAction] = useState(null);
  const [actionError, setActionError] = useState('');
  const [actionResult, setActionResult] = useState(null);

  const [pheromoneResource, setPheromoneResource] = useState('');
  const [pheromoneType, setPheromoneType] = useState('success');

  const executeAction = async (actionId, path, body = {}, customSuccess = null) => {
    setBusyAction(actionId);
    setActionError('');
    setActionResult(null);
    try {
      const data = await postJson(path, body);
      setActionResult(customSuccess || data.message || 'Operation successful');
      return data;
    } catch (err) {
      setActionError(`${actionId} failed: ${err.message}`);
      return null;
    } finally {
      setBusyAction(null);
    }
  };

  const handlePheromone = async (e, actionType) => {
    e.preventDefault();
    if (!pheromoneResource.trim()) return;
    
    let path = `/api/v1/pheromones/${actionType}`;
    await executeAction(`pheromone-${actionType}`, path, {
      resource: pheromoneResource,
      type: pheromoneType,
      amount: actionType === 'deposit' ? 1.0 : undefined
    }, `Pheromone ${actionType} triggered on ${pheromoneResource}`);
  };

  return (
    <div className="council-dashboard__body" aria-label="Sovereignty Controls">
      <div className="council-dashboard__detail">
        
        {(actionError || actionResult) && (
          <div className="council-dashboard__section">
             {actionError && <p className="council-dashboard__error">{actionError}</p>}
             {actionResult && <p className="council-dashboard__badge is-ok" style={{display: 'inline-block'}}>{actionResult}</p>}
          </div>
        )}

        <section className="council-dashboard__section">
          <h3>
            <Power size={14} aria-hidden="true" /> Hibernation Engine
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '12px' }}>
            Force the agent superorganism to dump volatile memory to disk and pause background workers.
          </p>
          <button 
            type="button" 
            className="is-reject"
            onClick={() => {
              if (window.confirm('Trigger emergency hibernation?')) {
                executeAction('hibernation', '/api/v1/hibernation/run')
              }
            }}
            disabled={busyAction !== null}
          >
            <Power size={14} /> Trigger Hibernation
          </button>
        </section>

        <section className="council-dashboard__section">
          <h3>
            <RotateCcw size={14} aria-hidden="true" /> System Rollbacks
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '12px' }}>
            Manage the V7 snapshot ledgers. 
          </p>
          <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
            <button 
              type="button" 
              onClick={() => executeAction('register-rollback', '/api/v1/runtime/rollbacks/register')}
              disabled={busyAction !== null}
            >
              <Box size={14} /> Register Snapshot
            </button>
            <button 
              type="button" 
              className="is-reject"
              onClick={() => {
                if (window.confirm('Prune old snapshots? This cannot be undone.')) {
                  executeAction('prune-rollbacks', '/api/v1/runtime/rollbacks/prune')
                }
              }}
              disabled={busyAction !== null}
            >
              <RotateCcw size={14} /> Prune Old Snapshots
            </button>
          </div>
        </section>

        <section className="council-dashboard__section">
          <h3>
            <Activity size={14} aria-hidden="true" /> Pheromone Injection
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '12px' }}>
            Manually inject or decay stigmergy pheromones on specific resources to steer autonomous workers.
          </p>
          <form className="council-dashboard__originate">
            <input
              type="text"
              className="council-dashboard__origin-files"
              style={{ marginBottom: '4px' }}
              value={pheromoneResource}
              onChange={(e) => setPheromoneResource(e.target.value)}
              placeholder="Resource (e.g. /frontend/src/App.jsx)"
              required
            />
            <select 
              className="council-dashboard__origin-files" 
              style={{ marginBottom: '8px', background: 'rgba(255,255,255,0.05)' }}
              value={pheromoneType}
              onChange={(e) => setPheromoneType(e.target.value)}
            >
              <option value="success">Success (Green)</option>
              <option value="danger">Danger (Red)</option>
              <option value="warning">Warning (Yellow)</option>
            </select>

            <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
              <button 
                type="submit" 
                onClick={(e) => handlePheromone(e, 'deposit')}
                disabled={busyAction !== null || !pheromoneResource.trim()}
              >
                <Droplet size={14} /> Deposit
              </button>
              <button 
                type="submit" 
                onClick={(e) => handlePheromone(e, 'reinforce')}
                disabled={busyAction !== null || !pheromoneResource.trim()}
              >
                <Zap size={14} /> Reinforce
              </button>
              <button 
                type="submit" 
                className="is-reject"
                onClick={(e) => handlePheromone(e, 'decay')}
                disabled={busyAction !== null || !pheromoneResource.trim()}
              >
                <Wind size={14} /> Decay
              </button>
            </div>
          </form>
        </section>

      </div>
    </div>
  );
}
