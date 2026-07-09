import React, { useEffect, useState } from 'react';
import HUDPanel from '../components/HUDPanel';

export default function MemoryBrowser({ onClose }) {
  const [experiences, setExperiences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadExperiences() {
      try {
        const response = await fetch('/api/v1/files/read', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: '.aios/memory/experiences.jsonl' })
        });
        
        if (!response.ok) {
          throw new Error('Failed to load experiences.jsonl');
        }
        
        const data = await response.json();
        const content = data.content || '';
        
        // Parse JSONL
        const parsed = content.trim().split('\n').filter(Boolean).map(line => {
          try {
            return JSON.parse(line);
          } catch (e) {
            return null;
          }
        }).filter(Boolean);
        
        setExperiences(parsed.reverse()); // Newest first
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    
    loadExperiences();
  }, []);

  return (
    <HUDPanel
      id="memory-browser"
      title="Memory Browser"
      tint="purple"
      defaultPosition={{ x: window.innerWidth / 2 - 250, y: window.innerHeight / 2 - 200 }}
      defaultSize={{ width: 500, height: 400 }}
      onClose={onClose}
    >
      <div style={{ padding: '16px', color: 'var(--foreground)', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ fontSize: '14px', marginBottom: '12px', color: 'var(--ag-text-purple)' }}>
          Experience Accumulator
        </h3>
        
        {loading ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>Loading memories...</div>
        ) : error ? (
          <div style={{ fontSize: '12px', color: 'var(--ag-text-amber)' }}>Error: {error}</div>
        ) : experiences.length === 0 ? (
          <div style={{ fontSize: '12px', opacity: 0.6 }}>No experiences logged.</div>
        ) : (
          <div style={{ overflowY: 'auto', flex: 1, paddingRight: '8px' }}>
            {experiences.map((exp, idx) => (
              <div key={idx} style={{ 
                marginBottom: '16px', 
                padding: '12px',
                background: 'var(--ag-surface-purple)',
                border: '1px solid rgba(128, 90, 213, 0.2)',
                borderRadius: '6px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <strong style={{ fontSize: '12px', color: '#e9d8fd' }}>
                    {exp.task_id || 'Unknown Task'}
                  </strong>
                  <span style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                    {exp.ts ? new Date(exp.ts).toLocaleString() : 'Unknown Time'}
                  </span>
                </div>
                
                {exp.goal && (
                  <div style={{ fontSize: '11px', marginBottom: '8px' }}>
                    <span style={{ color: 'var(--muted-foreground)' }}>Goal:</span> {exp.goal}
                  </div>
                )}
                
                {exp.outcome && (
                  <div style={{ fontSize: '11px', marginBottom: '8px' }}>
                    <span style={{ color: 'var(--muted-foreground)' }}>Outcome:</span>{' '}
                    <span style={{ color: exp.outcome.includes('success') ? 'var(--ag-text-cyan)' : 'var(--ag-text-amber)' }}>
                      {exp.outcome}
                    </span>
                  </div>
                )}
                
                {exp.lessons && (
                  <div style={{ fontSize: '11px' }}>
                    <span style={{ color: 'var(--muted-foreground)' }}>Lesson:</span>{' '}
                    <span style={{ color: '#d6bcfa' }}>{exp.lessons}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </HUDPanel>
  );
}
