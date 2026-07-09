import React, { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { Activity, Server, Cpu, Database, Network } from 'lucide-react';

export default function EcosystemDashboard({ onClose }) {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadMetrics() {
      try {
        const response = await fetch('/api/v1/development/metrics');
        if (!response.ok) {
          throw new Error('Failed to load metrics');
        }
        const data = await response.json();
        setMetrics(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    
    loadMetrics();
    const interval = setInterval(loadMetrics, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <HUDPanel
      id="ecosystem-dashboard"
      title="Ecosystem Health"
      tint="green"
      defaultPosition={{ x: 50, y: 50 }}
      defaultSize={{ width: 450, height: 400 }}
      onClose={onClose}
    >
      <div style={{ padding: '16px', color: 'var(--foreground)', height: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity style={{ color: 'var(--ag-text-green)' }} size={16} />
          <h3 style={{ fontSize: '14px', margin: 0, color: 'var(--ag-text-green)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            System Vitality
          </h3>
        </div>
        
        {loading && !metrics ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Scanning ecosystem...</div>
        ) : error ? (
          <div style={{ fontSize: '12px', color: 'var(--ag-text-red)' }}>Error: {error}</div>
        ) : !metrics ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>No metrics available.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ 
              background: 'rgba(74, 222, 128, 0.1)', 
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Server size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Memory Integration</strong>
              </div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#bbf7d0' }}>
                {metrics.memory_integration_score ? `${(metrics.memory_integration_score * 100).toFixed(1)}%` : 'N/A'}
              </div>
            </div>

            <div style={{ 
              background: 'rgba(74, 222, 128, 0.1)', 
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Database size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Fact Consistency</strong>
              </div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#bbf7d0' }}>
                {metrics.fact_consistency ? `${(metrics.fact_consistency * 100).toFixed(1)}%` : 'N/A'}
              </div>
            </div>

            <div style={{ 
              background: 'rgba(74, 222, 128, 0.1)', 
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px',
              gridColumn: '1 / -1'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Cpu size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Active Models</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#bbf7d0', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {metrics.active_models && metrics.active_models.length > 0 
                  ? metrics.active_models.map(m => (
                      <span key={m} style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px' }}>{m}</span>
                    ))
                  : 'Ollama Auto-Routing'}
              </div>
            </div>

            <div style={{ 
              background: 'rgba(74, 222, 128, 0.1)', 
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px',
              gridColumn: '1 / -1'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Network size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Recent Tasks</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#bbf7d0' }}>
                Completed: {metrics.tasks_completed || 0} | 
                Failed: {metrics.tasks_failed || 0}
              </div>
            </div>
          </div>
        )}
      </div>
    </HUDPanel>
  );
}
