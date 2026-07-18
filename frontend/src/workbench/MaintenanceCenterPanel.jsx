import { useState, useEffect } from 'react';
import { fetchMaintenanceFindings, fetchMaintenanceScans } from '../superbrain/lib/aiosAdapter';

export default function MaintenanceCenterPanel() {
  const [findings, setFindings] = useState([]);
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    Promise.all([fetchMaintenanceFindings(), fetchMaintenanceScans()]).then(
      ([findingsData, scansData]) => {
        if (mounted) {
          setFindings(findingsData);
          setScans(scansData);
          setLoading(false);
        }
      }
    );
    return () => { mounted = false; };
  }, []);

  return (
    <div className="gagos-panel">
      <h3>Maintenance Lifecycle Engine</h3>
      
      <div className="gagos-panel-section">
        <h4>Recent Scans</h4>
        {loading ? (
          <p>Loading scans...</p>
        ) : scans.length === 0 ? (
          <p>No recent scans.</p>
        ) : (
          <ul>
            {scans.map((s) => (
              <li key={s.id || Math.random()}>
                <strong>{s.strategy || 'Unknown Strategy'}</strong>
                <span> - {s.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="gagos-panel-section">
        <h4>Durable Findings</h4>
        {loading ? (
          <p>Loading findings...</p>
        ) : findings.length === 0 ? (
          <p>No durable findings reported.</p>
        ) : (
          <ul>
            {findings.map((f) => (
              <li key={f.id || Math.random()}>
                <strong>{f.severity}</strong>: {f.description}
                <small> ({f.status})</small>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
