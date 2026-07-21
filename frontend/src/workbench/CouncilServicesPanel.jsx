import { useCallback, useEffect, useState } from 'react';
import { Server, Play, Square, FileText, Slash } from 'lucide-react';
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

export default function CouncilServicesPanel() {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyAction, setBusyAction] = useState(null);
  
  const [rejectMissionId, setRejectMissionId] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [rejectBusy, setRejectBusy] = useState(false);
  
  const [reportMissionId, setReportMissionId] = useState('');
  const [reportData, setReportData] = useState(null);
  const [reportBusy, setReportBusy] = useState(false);

  const loadServices = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchJson('/api/v1/council/services', signal);
      setServices(asArray(data.services));
    } catch (err) {
      if (err?.name !== 'AbortError') setError('Council services offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void loadServices(ctrl.signal);
    return () => ctrl.abort();
  }, [loadServices]);

  const toggleService = async (serviceName, start) => {
    setBusyAction(serviceName);
    try {
      await postJson(`/api/v1/council/services/${encodeURIComponent(serviceName)}/${start ? 'start' : 'stop'}`);
      void loadServices();
    } catch (err) {
      alert(`Could not toggle service ${serviceName}`);
    } finally {
      setBusyAction(null);
    }
  };

  const handleReject = async (e) => {
    e.preventDefault();
    if (!rejectMissionId.trim()) return;
    setRejectBusy(true);
    try {
      await postJson('/api/v1/council/reject', { missionId: rejectMissionId, reason: rejectReason });
      setRejectMissionId('');
      setRejectReason('');
      alert('Mission rejected.');
    } catch (err) {
      alert('Failed to reject mission: ' + err.message);
    } finally {
      setRejectBusy(false);
    }
  };

  const handleReport = async (e) => {
    e.preventDefault();
    if (!reportMissionId.trim()) return;
    setReportBusy(true);
    setReportData(null);
    try {
      const data = await fetchJson(`/api/v1/council/reports/${encodeURIComponent(reportMissionId)}`);
      setReportData(data);
    } catch (err) {
      alert('Report not found or error loading.');
    } finally {
      setReportBusy(false);
    }
  };

  return (
    <div className="council-dashboard__body" aria-label="Council Services">
      <div className="council-dashboard__detail">
        
        <section className="council-dashboard__section">
          <h3>
            <Server size={14} aria-hidden="true" /> Daemon Workers
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Background autonomic services operating in the Council space.
          </p>
          {loading ? (
            <p className="council-dashboard__muted">Loading services...</p>
          ) : error ? (
            <p className="council-dashboard__error">{error}</p>
          ) : services.length === 0 ? (
            <p className="council-dashboard__muted">No services found.</p>
          ) : (
            services.map((svc) => (
              <div key={svc.name} className="council-dashboard__route" style={{ display: 'flex', alignItems: 'center' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <span className={`council-dashboard__risk-dot is-${svc.running ? 'ok' : 'danger'}`} />
                    <strong>{svc.name}</strong>
                  </div>
                  <div className="council-dashboard__muted" style={{ fontSize: '0.85em', marginTop: '2px' }}>
                    {svc.description}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={busyAction === svc.name}
                  onClick={() => toggleService(svc.name, !svc.running)}
                  aria-label={`Toggle ${svc.name}`}
                  className={svc.running ? 'is-reject' : ''}
                  style={{ padding: '4px 8px' }}
                >
                  {svc.running ? <Square size={12} /> : <Play size={12} />}
                </button>
              </div>
            ))
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <FileText size={14} aria-hidden="true" /> Fetch Mission Report
          </h3>
          <form className="council-dashboard__originate" onSubmit={handleReport}>
            <input
              type="text"
              className="council-dashboard__origin-files"
              value={reportMissionId}
              onChange={(e) => setReportMissionId(e.target.value)}
              placeholder="Mission ID (e.g. mission-123)"
              required
            />
            <button type="submit" disabled={reportBusy}>
              {reportBusy ? 'Fetching...' : 'Fetch Report'}
            </button>
          </form>
          {reportData && (
             <div className="council-dashboard__verdicts" style={{ marginTop: '12px' }}>
                <pre style={{ margin: 0, fontSize: '10px', overflowX: 'auto' }}>
                  {JSON.stringify(reportData, null, 2)}
                </pre>
             </div>
          )}
        </section>

        <section className="council-dashboard__section">
          <h3>
            <Slash size={14} aria-hidden="true" /> Manually Reject Mission
          </h3>
          <p className="council-dashboard__muted" style={{ marginBottom: '8px' }}>
            Force a mission to fail immediately with a custom reason.
          </p>
          <form className="council-dashboard__originate" onSubmit={handleReject}>
            <input
              type="text"
              className="council-dashboard__origin-files"
              style={{ marginBottom: '4px' }}
              value={rejectMissionId}
              onChange={(e) => setRejectMissionId(e.target.value)}
              placeholder="Mission ID"
              required
            />
            <input
              type="text"
              className="council-dashboard__origin-files"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Rejection Reason"
              required
            />
            <button type="submit" className="is-reject" disabled={rejectBusy}>
              Force Reject
            </button>
          </form>
        </section>

      </div>
    </div>
  );
}
