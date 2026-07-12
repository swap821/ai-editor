import { useState, useEffect } from 'react';
import { AIOS_BASE } from '../superbrain/lib/aiosAdapter';
import './TrustHalo.css';

const POLL_INTERVAL_MS = 30000;

function computeTrustLevel(metrics) {
  if (!metrics) return 'unknown';
  const interventionRate = metrics.human_intervention_rate || 0;
  const verificationCoverage = metrics.verification_coverage || 0;
  // Green: low intervention, high verification
  if (interventionRate < 0.3 && verificationCoverage > 0.7) return 'healthy';
  // Red: high intervention or very low verification
  if (interventionRate > 0.7 || verificationCoverage < 0.3) return 'critical';
  // Amber: middle ground
  return 'attention';
}

export default function TrustHalo() {
  const [trustLevel, setTrustLevel] = useState('unknown');


  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const resp = await fetch(`${AIOS_BASE}/api/v1/development/metrics`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (cancelled) return;

        setTrustLevel(computeTrustLevel(data));
      } catch {
        // Offline or error — show unknown
      }
    }
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <div className={`trust-halo trust-halo--${trustLevel}`} aria-label={`System trust: ${trustLevel}`}>
      <div className="trust-halo__ring" />
      <div className="trust-halo__label">{trustLevel}</div>
    </div>
  );
}

export { computeTrustLevel };
