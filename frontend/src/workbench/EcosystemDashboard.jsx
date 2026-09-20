import React, { useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { Activity, Server, Cpu, Database, Network } from 'lucide-react';
import { API_HEADERS } from '../config';
import { useResource } from '../livingMirror/resource';
import { parseV10EcosystemStatus } from '../livingMirror/v10Status';

const V10_READ = Object.freeze({ headers: API_HEADERS });
const neverEmpty = () => false;
const count = (value, label) => value === null ? `${label} unavailable` : `${value} ${label}`;

export default function EcosystemDashboard({ onClose }) {
  const resource = useResource('/api/v1/v10/status', parseV10EcosystemStatus, neverEmpty, V10_READ);
  const status = resource.data;

  useEffect(() => {
    const interval = setInterval(resource.refresh, 15000);
    return () => clearInterval(interval);
  }, [resource.refresh]);

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

        {resource.status === 'loading' && !status ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Reading ecosystem status...</div>
        ) : resource.error && !status ? (
          <div role="alert" style={{ fontSize: '12px', color: 'var(--ag-text-red)' }}>{resource.error}</div>
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
                {!ecosystem
                  ? 'Ecosystem scanner status unavailable'
                  : ecosystemScan === undefined
                    ? 'Scan state unavailable'
                    : ecosystemScan === null
                      ? 'available · not scanned'
                      : `${count(ecosystemScan.findingCount, 'finding(s)')} · ${count(ecosystemScan.networkCalls, 'network calls')}`}
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
                {!constitution
                  ? 'Constitution status unavailable'
                  : `${count(constitution.casteCount, 'castes')} · ${constitution.frozenCoreProtected === null ? 'frozen-core status unavailable' : constitution.frozenCoreProtected ? 'frozen protected' : 'needs review'}`}
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
                {!repoMap
                  ? 'RepoMap status unavailable'
                  : repoMap.lastScan === undefined
                    ? 'Symbol scan state unavailable'
                    : repoMap.lastScan === null
                      ? 'available · no symbol scan recorded'
                      : `${count(repoMap.lastScan.symbolCount, 'symbols')} · ${count(repoMap.lastScan.evidenceFileCount, 'files')} · ${repoMap.activation ?? 'activation unavailable'}`}
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
                Meta-loop: {metaLoop ? `${metaLoop.safetyStatus ?? 'safety status unavailable'} · ${count(metaLoop.proposalCount, 'proposal(s)')}` : 'Meta-loop status unavailable'} | Council memory: {councilMemory ? count(councilMemory.deliberationCount, 'deliberation(s)') : 'Council memory status unavailable'}
              </div>
            </div>
          </div>
        )}
        {resource.error && status && <div role="alert" style={{ fontSize: '12px', color: 'var(--ag-text-red)' }}>{resource.error} Last-known ecosystem records are shown above.</div>}
      </div>
    </HUDPanel>
  );
}
