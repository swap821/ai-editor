import { useState } from 'react';
import { Database, Zap, Archive, Scissors, ShieldAlert, AlignLeft } from 'lucide-react';
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

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export default function MemoryOperationsPanel() {
  const [busyAction, setBusyAction] = useState(null);
  const [actionError, setActionError] = useState('');
  const [actionResult, setActionResult] = useState(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);

  const [reconcileFact1, setReconcileFact1] = useState('');
  const [reconcileFact2, setReconcileFact2] = useState('');

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

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    const data = await executeAction('search', '/api/v1/memory/search', { query: searchQuery });
    if (data) {
      setSearchResults(asArray(data.results));
    }
  };

  const handleReconcile = async (e) => {
    e.preventDefault();
    if (!reconcileFact1.trim() || !reconcileFact2.trim()) return;
    await executeAction('reconcile', '/api/v1/memory/facts/reconcile', { 
      fact1: reconcileFact1, 
      fact2: reconcileFact2 
    });
  };

  return (
    <div className="council-dashboard__body" aria-label="Memory Operations">
      <div className="council-dashboard__detail">
        
        {/* Status bar for actions */}
        {(actionError || actionResult) && (
          <div className="council-dashboard__section">
             {actionError && <p className="council-dashboard__error">{actionError}</p>}
             {actionResult && <p className="council-dashboard__badge is-ok" style={{display: 'inline-block'}}>{actionResult}</p>}
          </div>
        )}

        <section className="council-dashboard__section">
          <h3>
            <Zap size={14} aria-hidden="true" /> Memory Management
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '12px' }}>
            Force the autonomic systems to compress the working context window or move short-term tokens to long-term FAISS storage.
          </p>
          <div className="council-dashboard__decision-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
            <button 
              type="button" 
              onClick={() => executeAction('compact', '/api/v1/memory/compact')}
              disabled={busyAction !== null}
            >
              <Scissors size={14} /> Compact Context
            </button>
            <button 
              type="button" 
              onClick={() => executeAction('consolidate', '/api/v1/memory/consolidate')}
              disabled={busyAction !== null}
            >
              <Archive size={14} /> Consolidate to LTM
            </button>
          </div>
        </section>

        <section className="council-dashboard__section council-dashboard__split">
          <div style={{ flex: 1 }}>
            <h3><Database size={14} aria-hidden="true" /> Raw Vector Search</h3>
            <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>Debug the LTM embeddings.</p>
            <form className="council-dashboard__originate" onSubmit={handleSearch}>
              <input
                type="text"
                className="council-dashboard__origin-files"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search vector space..."
                required
              />
              <button type="submit" disabled={busyAction !== null}>Search</button>
            </form>
            
            {searchResults !== null && (
              <div className="council-dashboard__verdicts" style={{ marginTop: '16px' }}>
                {searchResults.length === 0 ? (
                  <p className="council-dashboard__muted">No vectors found.</p>
                ) : (
                  searchResults.map((res, i) => (
                    <div key={i} className="council-dashboard__route" style={{ display: 'block', padding: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <strong className="council-dashboard__badge is-ok">Score: {Math.round(res.score * 100)}%</strong>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.85em', whiteSpace: 'pre-wrap' }}>{res.text || res.content}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </section>

        <section className="council-dashboard__section">
          <h3>
            <ShieldAlert size={14} aria-hidden="true" /> Reconcile Facts
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Manually trigger fact resolution if two pieces of knowledge contradict.
          </p>
          <form className="council-dashboard__originate" onSubmit={handleReconcile}>
            <input
              type="text"
              className="council-dashboard__origin-files"
              style={{ marginBottom: '4px' }}
              value={reconcileFact1}
              onChange={(e) => setReconcileFact1(e.target.value)}
              placeholder="Fact A ID or text..."
              required
            />
            <input
              type="text"
              className="council-dashboard__origin-files"
              value={reconcileFact2}
              onChange={(e) => setReconcileFact2(e.target.value)}
              placeholder="Fact B ID or text..."
              required
            />
            <button type="submit" disabled={busyAction !== null}>
              <AlignLeft size={14} /> Reconcile
            </button>
          </form>
        </section>

      </div>
    </div>
  );
}
