import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Battery, Cloud, Cpu, MemoryStick, Users } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

async function fetchResourceStatus(signal) {
  const response = await fetch(`${API_BASE}/api/v1/resource/status`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Unsupported resource status response');
  return data;
}

const valueOrUnavailable = (value) => value === null || value === undefined ? 'unavailable' : value;
const costOrUnavailable = (value) => typeof value === 'number' && Number.isFinite(value) ? `$${value.toFixed(2)}` : 'unavailable';

export default function BudgetMicroBar() {
  // Real process resource/budget mode (aios/api/routes/sovereignty.py's
  // BudgetGuard.snapshot()). There is no "allowance" or per-ganglion cost
  // breakdown concept in the backend -- that was fabricated UI; this shows
  // what actually exists.
  const [status, setStatus] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback((signal) => {
    fetchResourceStatus(signal)
      .then((data) => setStatus((prev) => ({ ...(prev || {}), ...data })))
      .catch((err) => {
        if (err?.name !== 'AbortError') console.error('Failed to fetch resource status', err);
      });
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    const interval = setInterval(() => load(), 15000);
    return () => {
      ctrl.abort();
      clearInterval(interval);
    };
  }, [load]);

  const getStateColor = (mode) => {
    switch (mode) {
      case 'hibernation': return 'var(--aura-hibernation, #60a5fa)';
      case 'conservation': return 'var(--aura-conservation, #fbbf24)';
      case 'normal': return 'var(--aura-normal, #7bf5fb)';
      case 'unavailable': return 'var(--aura-conservation, #fbbf24)';
      default: return 'var(--aura-conservation, #fbbf24)';
    }
  };

  const mode = typeof status?.mode === 'string' && status.mode ? status.mode : 'unavailable';
  const color = getStateColor(mode);
  const pct = (value) => (typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : 'unavailable');

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
        title={`Resource mode: ${mode.toUpperCase()}`}
      >
        <Battery size={14} color={color} />
        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color, textTransform: 'uppercase' }}>
          {mode}
        </span>
        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)' }}>
          {costOrUnavailable(status?.estimated_cost)}
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
              <span style={{ color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>Estimated Cost</span>
              <span style={{ color: 'var(--text-1)', fontWeight: 600 }}>{costOrUnavailable(status?.estimated_cost)}</span>
            </div>

            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Live Resource Status
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>
                  <Cloud size={12} /> <span>Cloud calls</span>
                </div>
                <span style={{ color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' }}>
                  {valueOrUnavailable(status?.cloud_calls)}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>
                  <Users size={12} /> <span>Workers</span>
                </div>
                <span style={{ color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' }}>
                  {valueOrUnavailable(status?.worker_count)}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>
                  <Cpu size={12} /> <span>CPU pressure</span>
                </div>
                <span style={{ color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' }}>
                  {pct(status?.cpu_pressure)}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>
                  <MemoryStick size={12} /> <span>Memory pressure</span>
                </div>
                <span style={{ color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)' }}>
                  {pct(status?.memory_pressure)}
                </span>
              </div>
            </div>

            <div style={{ marginTop: 12, fontSize: 'var(--text-xs)', color: status?.cloud_allowed === false ? 'var(--danger, #f87171)' : 'var(--text-3)' }}>
              {valueOrUnavailable(status?.reason)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
