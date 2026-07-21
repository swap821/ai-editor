import React, { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { Activity, Server, Cpu, Database, Network } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

export default function EcosystemDashboard({ onClose }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadStatus() {
      try {
        const response = await fetch(`${API_BASE}/api/v1/v10/status`, {
          credentials: 'include',
          headers: API_HEADERS,
        });
        if (!response.ok) {
          throw new Error('Failed to load v10 truth surface');
        }
        const data = await response.json();
        setStatus(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadStatus();
    const interval = setInterval(loadStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const ecosystem = status?.ecosystem;
  const ecosystemScan = ecosystem?.lastScan;
  const constitution = status?.constitution;
  const repoMap = status?.symbolRepoMap;
  const metaLoop = status?.metaLoop;
  const councilMemory = status?.councilMemory;

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
            Local Ecosystem Evidence
          </h3>
        </div>

        {loading && !status ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Reading ecosystem status...</div>
        ) : error ? (
          <div style={{ fontSize: '12px', color: 'var(--ag-text-red)' }}>Error: {error}</div>
        ) : !status ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>No v10 status available.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{
              background: 'rgba(74, 222, 128, 0.1)',
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Server size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Ecosystem scanner</strong>
              </div>
              <div style={{ fontSize: '13px', color: '#bbf7d0' }}>
                {ecosystemScan
                  ? `${ecosystemScan.findingCount ?? 0} finding(s) · ${ecosystemScan.networkCalls ?? 0} network calls`
                  : 'available · not scanned'}
              </div>
            </div>

            <div style={{
              background: 'rgba(74, 222, 128, 0.1)',
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Database size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Constitution</strong>
              </div>
              <div style={{ fontSize: '13px', color: '#bbf7d0' }}>
                {constitution
                  ? `${constitution.casteCount ?? 0} castes · ${constitution.frozenCoreProtected ? 'frozen protected' : 'needs review'}`
                  : 'offline'}
              </div>
            </div>

            <div style={{
              background: 'rgba(74, 222, 128, 0.1)',
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px',
              gridColumn: '1 / -1',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Cpu size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Symbol RepoMap</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#bbf7d0', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {repoMap?.lastScan
                  ? `${repoMap.lastScan.symbolCount ?? 0} symbols · ${repoMap.lastScan.evidenceFileCount ?? 0} files · ${repoMap.activation}`
                  : 'available · no symbol scan recorded'}
              </div>
            </div>

            <div style={{
              background: 'rgba(74, 222, 128, 0.1)',
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '12px',
              borderRadius: '6px',
              gridColumn: '1 / -1',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#86efac' }}>
                <Network size={14} />
                <strong style={{ fontSize: '11px', textTransform: 'uppercase' }}>Meta-loop and council memory</strong>
              </div>
              <div style={{ fontSize: '12px', color: '#bbf7d0' }}>
                Meta-loop: {metaLoop ? `${metaLoop.safetyStatus} · ${metaLoop.proposalCount ?? 0} proposal(s)` : 'offline'} | Council memory: {councilMemory ? `${councilMemory.deliberationCount ?? 0} deliberation(s)` : 'offline'}
              </div>
            </div>
          </div>
        )}
      </div>
    </HUDPanel>
  );
}
