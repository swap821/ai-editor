import React, { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { ShieldAlert, Activity, CheckCircle, Shield } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

export default function VultureFeed({ onClose }) {
  const [vulture, setVulture] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadVultureStatus() {
      try {
        const response = await fetch(`${API_BASE}/api/v1/v10/status`, {
          credentials: 'include',
          headers: API_HEADERS,
        });
        if (!response.ok) {
          throw new Error('Failed to load v10 truth surface');
        }
        const data = await response.json();
        setVulture(data.vulture || null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadVultureStatus();
    const interval = setInterval(loadVultureStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const lastScan = vulture?.lastScan;
  const findings = Array.isArray(lastScan?.topFindings) ? lastScan.topFindings : [];

  return (
    <HUDPanel
      id="vulture-feed"
      title="Vulture Security Feed"
      tint="amber"
      defaultPosition={{ x: window.innerWidth - 420, y: window.innerHeight - 380 }}
      defaultSize={{ width: 400, height: 350 }}
      onClose={onClose}
    >
      <div style={{ padding: '16px', color: 'var(--foreground)', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <Shield style={{ color: 'var(--ag-text-amber)' }} size={16} />
          <h3 style={{ fontSize: '14px', margin: 0, color: 'var(--ag-text-amber)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Immune Evidence
          </h3>
          <div
            aria-hidden="true"
            style={{
              marginLeft: 'auto',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: 'var(--ag-text-amber)',
              boxShadow: '0 0 8px var(--ag-text-amber)',
            }}
          />
        </div>

        {loading && !vulture ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Reading immune scanner status...</div>
        ) : error ? (
          <div style={{ fontSize: '12px', color: 'var(--ag-text-red)' }}>Error: {error}</div>
        ) : !vulture ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Vulture status unavailable.</div>
        ) : !lastScan ? (
          <div style={{ fontSize: '12px', opacity: 0.7, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle size={14} style={{ color: 'var(--ag-text-green)' }} />
            Scanner available; no explicit vulture scan has run.
          </div>
        ) : findings.length === 0 ? (
          <div style={{ fontSize: '12px', opacity: 0.7, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle size={14} style={{ color: 'var(--ag-text-green)' }} />
            Last scan found 0 quarantine proposals.
          </div>
        ) : (
          <div style={{ overflowY: 'auto', flex: 1, paddingRight: '8px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
              {lastScan.findingCount ?? findings.length} finding(s) · {lastScan.cloudCalls ?? 0} cloud calls · {lastScan.writesPerformed ? 'writes performed' : 'no writes'}
            </div>
            {findings.map((finding, idx) => {
              const isBlock = finding.severity === 'critical' || finding.severity === 'high';
              return (
                <div
                  key={`${finding.kind}-${finding.targetId}-${idx}`}
                  style={{
                    padding: '12px',
                    background: isBlock ? 'rgba(251, 146, 60, 0.1)' : 'var(--ag-surface-amber)',
                    border: `1px solid ${isBlock ? 'rgba(251, 146, 60, 0.4)' : 'rgba(251, 146, 60, 0.2)'}`,
                    borderRadius: '6px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {isBlock ? (
                        <ShieldAlert size={14} style={{ color: '#fb923c' }} />
                      ) : (
                        <Activity size={14} style={{ color: '#fcd34d' }} />
                      )}
                      <strong style={{ fontSize: '12px', color: isBlock ? '#fb923c' : '#fcd34d' }}>
                        {finding.kind || 'finding'}
                      </strong>
                    </div>
                    <span style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                      {finding.severity || 'evidence'}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '4px' }}>
                    {finding.recommendation || 'Review as proposal evidence.'}
                  </div>
                  {finding.targetId ? (
                    <div style={{ fontSize: '10px', marginTop: '6px', color: 'rgba(251, 146, 60, 0.8)' }}>
                      Source: {finding.targetId}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </HUDPanel>
  );
}
