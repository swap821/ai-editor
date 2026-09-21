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

class InvalidAlignmentPayload extends Error {}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isNonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function isRate(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isCounterMap(value) {
  return isRecord(value) && Object.values(value).every(isNonNegativeInteger);
}

function parseAlignmentPayload(payload) {
  if (!isRecord(payload)) throw new InvalidAlignmentPayload('alignment summary must be an object');

  const countFields = [
    'total_turns',
    'corrected_turns',
    'human_feedback_count',
  ];
  if (!countFields.every((field) => isNonNegativeInteger(payload[field]))) {
    throw new InvalidAlignmentPayload('alignment counts are incomplete');
  }

  const rateFields = [
    'correction_rate',
    'positive_feedback_rate',
    'ask_rate',
    'state_assumptions_rate',
  ];
  if (!rateFields.every((field) => isRate(payload[field]))) {
    throw new InvalidAlignmentPayload('alignment rates are incomplete');
  }

  const counterFields = [
    'outcomes',
    'by_intent',
    'by_communication_mode',
    'by_ambiguity_action',
    'corrected_fields',
    'issues',
  ];
  if (!counterFields.every((field) => isCounterMap(payload[field]))) {
    throw new InvalidAlignmentPayload('alignment counters are incomplete');
  }
  if (
    !Array.isArray(payload.repeated_patterns) ||
    !payload.repeated_patterns.every(isRecord) ||
    !Array.isArray(payload.recent) ||
    !payload.recent.every(isRecord) ||
    typeof payload.automatic_policy_updates !== 'boolean'
  ) {
    throw new InvalidAlignmentPayload('alignment evidence is incomplete');
  }

  return payload;
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
      // Real backend route (aios/api/routes/memory.py) — global diagnostic
      // alignment evidence, not conversation-corrections. There is no
      // conversation-scoped "/conversation/alignment" endpoint on the backend.
      const data = await fetchJson('/api/v1/alignment/evaluation', signal);
      setAlignmentState(parseAlignmentPayload(data));
      return { ok: true };
    } catch (err) {
      if (err?.name !== 'AbortError') {
        const message = err instanceof InvalidAlignmentPayload ? 'Alignment data unavailable' : 'Alignment data offline';
        setError(message);
        return { ok: false, error: message };
      }
      return { ok: false, error: 'Alignment request cancelled' };
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadAlignment(ctrl.signal);
    return () => ctrl.abort();
  }, [loadAlignment]);

  // There is no backend "force resync" primitive for a global alignment
  // frame (alignment corrections/feedback are session-scoped, requiring a
  // sessionId this HUD doesn't track). Rather than call a route that doesn't
  // exist, this refetches the current diagnostic summary.
  const handleSync = async () => {
    setSyncBusy(true);
    setSyncError('');
    setSyncMessage('');
    try {
      const refreshed = await loadAlignment();
      if (refreshed.ok) setSyncMessage('Refreshed');
      else setSyncError(`Refresh failed: ${refreshed.error}`);
    } catch (err) {
      setSyncError('Refresh failed: ' + err.message);
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
            Stored alignment-evaluation evidence; this is diagnostic history, not live conversation state.
          </p>
          {loading ? (
            <p className="council-dashboard__muted">Loading alignment...</p>
          ) : !alignmentState ? (
            <p className="council-dashboard__error">{error || 'Alignment data unavailable'}</p>
          ) : (
            <>
              {error && <p className="council-dashboard__error">{error}</p>}
              <div className="council-dashboard__verdicts" style={{ marginTop: '12px' }}>
                <pre style={{ margin: 0, fontSize: '10px', overflowX: 'auto' }}>
                  {JSON.stringify(alignmentState, null, 2)}
                </pre>
              </div>
            </>
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <RefreshCcw size={14} aria-hidden="true" /> Force Sync
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Refresh the stored diagnostic evaluation summary.
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
