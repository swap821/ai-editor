import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Battery, Zap, Shield, Eye, Settings } from 'lucide-react';
// import { subscribeCognition } from '../superbrain/lib/cognitionBus';

export default function BudgetMicroBar() {
  const [budget, setBudget] = useState({
    spent: 12.5,
    allowance: 50.0,
    state: 'normal', // hibernation, conservation, normal, expansion, feast
    breakdown: {
      plan: 2.1,
      security: 1.5,
      memory: 3.2,
      verify: 4.5,
      synthesis: 1.2
    }
  });
  
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    // Mock subscription
    // const unsubscribe = subscribeCognition('budget', (data) => setBudget(data));
    // return unsubscribe;
  }, []);

  const ratio = Math.min(1, budget.spent / budget.allowance);
  
  const getStateColor = (state) => {
    switch (state) {
      case 'hibernation': return 'var(--aura-hibernation, #60a5fa)';
      case 'conservation': return 'var(--aura-conservation, #fbbf24)';
      case 'normal': return 'var(--aura-normal, #7bf5fb)';
      case 'expansion': return 'var(--aura-expansion, #a78bfa)';
      case 'feast': return 'var(--aura-feast, #fbbf24)';
      default: return 'var(--aura-normal, #7bf5fb)';
    }
  };

  const color = getStateColor(budget.state);

  return (
    <div style={{ position: 'relative' }}>
      {/* Micro Bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-pill)',
          padding: '4px 12px',
          color: 'var(--text-1)',
          cursor: 'pointer',
          boxShadow: expanded ? `0 0 12px ${color}33` : 'none',
        }}
        title={`Energy State: ${budget.state.toUpperCase()}`}
      >
        <Battery size={14} color={color} />
        <div style={{ width: 60, height: 4, background: 'var(--surface-4)', borderRadius: 2, overflow: 'hidden' }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${ratio * 100}%` }}
            transition={{ duration: 1, ease: 'easeOut' }}
            style={{ height: '100%', background: color }}
          />
        </div>
        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color }}>
          ${budget.spent.toFixed(2)}
        </span>
      </button>

      {/* Expanded Details Panel */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 8,
              background: 'var(--ag-surface-base)',
              backdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
              border: 'var(--hairline)',
              borderRadius: 'var(--radius-md)',
              padding: 16,
              width: 280,
              zIndex: 100,
              boxShadow: 'var(--elevation-3)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <span style={{ color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>Daily Allowance</span>
              <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>${budget.allowance.toFixed(2)}</span>
            </div>
            
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Ganglion Cost Breakdown
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {Object.entries(budget.breakdown).map(([key, val]) => (
                <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>
                    {key === 'plan' && <Zap size={12} />}
                    {key === 'security' && <Shield size={12} />}
                    {key === 'memory' && <Settings size={12} />}
                    {key === 'verify' && <Eye size={12} />}
                    {key === 'synthesis' && <Battery size={12} />}
                    <span style={{ textTransform: 'capitalize' }}>{key}</span>
                  </div>
                  <span style={{ color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' }}>
                    ${val.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
