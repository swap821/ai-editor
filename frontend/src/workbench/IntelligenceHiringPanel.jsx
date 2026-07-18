import { useState, useEffect } from 'react';
import { fetchHiringProposals } from '../superbrain/lib/aiosAdapter';

export default function IntelligenceHiringPanel() {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetchHiringProposals().then((data) => {
      if (mounted) {
        setProposals(data);
        setLoading(false);
      }
    });
    return () => { mounted = false; };
  }, []);

  return (
    <div className="gagos-panel">
      <h3>Hiring Broker Proposals</h3>
      {loading ? (
        <p>Loading proposals...</p>
      ) : proposals.length === 0 ? (
        <p>No active hiring proposals.</p>
      ) : (
        <ul>
          {proposals.map((p, index) => (
            <li key={p.id || p.provider_id || `proposal-${index}`}>
              <strong>{p.model_name || p.provider_id}</strong>
              <span> - {p.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
