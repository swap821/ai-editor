import React, { useEffect, useState } from 'react';
import HUDPanel from '../components/HUDPanel';
import { subscribeSwarmHUD, getSwarmHUDState } from '../superbrain/lib/swarmHUDStore';

export default function CouncilDeliberationPanel({ onClose }) {
  const [swarmState, setSwarmState] = useState(getSwarmHUDState());

  useEffect(() => {
    return subscribeSwarmHUD((state) => {
      setSwarmState(state);
    });
  }, []);

  return (
    <HUDPanel
      id="council-panel"
      title="Council Deliberation"
      tint="purple"
      defaultPosition={{ x: window.innerWidth - 420, y: 80 }}
      defaultSize={{ width: 400, height: 350 }}
      onClose={onClose}
    >
      <div style={{ padding: '16px', color: 'var(--foreground)' }}>
        <h3 style={{ fontSize: '14px', marginBottom: '12px', color: 'var(--ag-text-cyan)' }}>
          Active Swarm State: {swarmState.active ? 'ENGAGED' : 'STANDBY'}
        </h3>
        
        <div style={{ marginBottom: '16px' }}>
          <strong style={{ display: 'block', fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '8px', letterSpacing: '0.05em' }}>
            Current Castes
          </strong>
          {swarmState.activeCastes.length === 0 ? (
            <span style={{ fontSize: '12px', opacity: 0.6 }}>No active castes</span>
          ) : (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {swarmState.activeCastes.map((caste, idx) => (
                <span key={idx} style={{ 
                  background: 'rgba(128, 90, 213, 0.2)', 
                  border: '1px solid rgba(128, 90, 213, 0.4)', 
                  padding: '4px 10px', 
                  borderRadius: '12px', 
                  fontSize: '11px',
                  color: '#d6bcfa'
                }}>
                  {caste}
                </span>
              ))}
            </div>
          )}
        </div>

        <div>
          <strong style={{ display: 'block', fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '8px', letterSpacing: '0.05em' }}>
            Subtask Plan
          </strong>
          {swarmState.plan.length === 0 ? (
            <span style={{ fontSize: '12px', opacity: 0.6 }}>Awaiting objective...</span>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {swarmState.plan.map((step, idx) => {
                const isCloud = swarmState.cloudIndices.includes(idx);
                const isCompleted = idx < swarmState.completedLegs;
                const isCurrent = idx === swarmState.completedLegs;
                return (
                  <li key={idx} style={{ 
                    padding: '4px 0', 
                    opacity: isCompleted ? 0.4 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                  }}>
                    <span style={{ 
                      width: '18px', 
                      height: '18px', 
                      borderRadius: '50%', 
                      border: isCurrent ? '1px solid var(--ag-text-cyan)' : '1px solid var(--border)',
                      background: isCompleted ? 'var(--ag-text-cyan)' : 'transparent',
                      color: isCompleted ? '#000' : 'inherit',
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '10px',
                      flexShrink: 0
                    }}>
                      {isCompleted ? '✓' : idx + 1}
                    </span>
                    <span style={{ flex: 1, textDecoration: isCompleted ? 'line-through' : 'none', lineHeight: '1.4' }}>
                      {step}
                    </span>
                    {isCloud && (
                      <span style={{ fontSize: '10px', color: '#d6bcfa', flexShrink: 0, padding: '2px 6px', background: 'rgba(128, 90, 213, 0.1)', borderRadius: '4px' }}>
                        Cloud
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </HUDPanel>
  );
}
