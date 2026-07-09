import React, { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { ShieldAlert, Activity, CheckCircle, Shield } from 'lucide-react';

export default function VultureFeed({ onClose }) {
  const [trails, setTrails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadTrails() {
      try {
        const response = await fetch('/api/v1/development/trails');
        if (!response.ok) {
          throw new Error('Failed to load security trails');
        }
        const data = await response.json();
        setTrails(data.trails || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    
    loadTrails();
    // Poll every 5 seconds
    const interval = setInterval(loadTrails, 5000);
    return () => clearInterval(interval);
  }, []);

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
            Live Audit Stream
          </h3>
          <div style={{ 
            marginLeft: 'auto', 
            width: '8px', 
            height: '8px', 
            borderRadius: '50%', 
            background: 'var(--ag-text-amber)',
            boxShadow: '0 0 8px var(--ag-text-amber)'
          }} />
        </div>
        
        {loading && trails.length === 0 ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Monitoring security boundaries...</div>
        ) : error ? (
          <div style={{ fontSize: '12px', color: 'var(--ag-text-red)' }}>Error: {error}</div>
        ) : trails.length === 0 ? (
          <div style={{ fontSize: '12px', opacity: 0.6, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle size={14} style={{ color: 'var(--ag-text-green)' }} />
            No security violations detected.
          </div>
        ) : (
          <div style={{ overflowY: 'auto', flex: 1, paddingRight: '8px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {trails.map((trail, idx) => {
              const isBlock = trail.action === 'block' || trail.severity === 'high';
              return (
                <div key={idx} style={{ 
                  padding: '12px',
                  background: isBlock ? 'rgba(251, 146, 60, 0.1)' : 'var(--ag-surface-amber)',
                  border: `1px solid ${isBlock ? 'rgba(251, 146, 60, 0.4)' : 'rgba(251, 146, 60, 0.2)'}`,
                  borderRadius: '6px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {isBlock ? (
                        <ShieldAlert size={14} style={{ color: '#fb923c' }} />
                      ) : (
                        <Activity size={14} style={{ color: '#fcd34d' }} />
                      )}
                      <strong style={{ fontSize: '12px', color: isBlock ? '#fb923c' : '#fcd34d' }}>
                        {trail.event || 'System Event'}
                      </strong>
                    </div>
                    <span style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                      {trail.ts ? new Date(trail.ts).toLocaleTimeString() : ''}
                    </span>
                  </div>
                  
                  {trail.details && (
                    <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '4px' }}>
                      {typeof trail.details === 'string' ? trail.details : JSON.stringify(trail.details)}
                    </div>
                  )}
                  {trail.agent && (
                    <div style={{ fontSize: '10px', marginTop: '6px', color: 'rgba(251, 146, 60, 0.8)' }}>
                      Source: {trail.agent}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </HUDPanel>
  );
}
