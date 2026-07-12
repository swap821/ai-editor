import { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { Sliders, Server, Cpu, Power } from 'lucide-react';
import { API_BASE, API_HEADERS } from '../config';

async function fetchJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    credentials: 'include',
    headers: API_HEADERS,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(path, body = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export default function SettingsPanel({ onClose }) {
  const [provider, setProvider] = useState('Ollama');
  const [autonomy, setAutonomy] = useState(true);
  const [theme, setTheme] = useState('Superbrain');

  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    const ctrl = new AbortController();
    fetchJson('/api/v1/system/config', ctrl.signal)
      .then((data) => {
        if (data.provider) setProvider(data.provider);
        if (typeof data.autonomy === 'boolean') setAutonomy(data.autonomy);
        if (data.theme) setTheme(data.theme);
      })
      .catch((err) => {
        if (err?.name !== 'AbortError') setLoadError('Could not load current settings; showing defaults.');
      });
    return () => ctrl.abort();
  }, []);

  return (
    <HUDPanel
      id="settings-panel"
      title="System Preferences"
      tint="base"
      defaultPosition={{ x: window.innerWidth / 2 - 200, y: window.innerHeight / 2 - 200 }}
      defaultSize={{ width: 400, height: 350 }}
      onClose={onClose}
    >
      <div style={{ padding: '20px', color: 'var(--foreground)', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {loadError && (
          <p style={{ fontSize: '11px', color: 'var(--danger)', margin: 0 }}>{loadError}</p>
        )}

        {/* LLM Provider */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <Server size={14} style={{ color: 'var(--ag-text-cyan)' }} />
            <strong style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>LLM Provider</strong>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', marginBottom: '8px' }}>
            Controlled by .env file (AIOS_LLM_MODEL, AIOS_BEDROCK_MODEL, AIOS_GEMINI_MODEL)
          </div>
          <div style={{ display: 'flex', gap: '8px', opacity: 0.5, pointerEvents: 'none' }}>
            {['Ollama', 'Bedrock', 'Gemini'].map(p => (
              <button
                key={p}
                onClick={() => setProvider(p)}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: provider === p ? 'rgba(123, 245, 251, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                  border: `1px solid ${provider === p ? 'var(--ag-text-cyan)' : 'var(--border)'}`,
                  color: provider === p ? '#fff' : 'var(--muted-foreground)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '12px'
                }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Autonomy Toggle */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <Cpu size={14} style={{ color: 'var(--ag-text-purple)' }} />
            <strong style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Earned Autonomy</strong>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', marginBottom: '8px' }}>
            Controlled by .env file (AIOS_EARNED_AUTONOMY)
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'not-allowed', opacity: 0.5 }}>
            <div style={{
              width: '40px',
              height: '20px',
              background: autonomy ? 'var(--ag-text-purple)' : 'rgba(255, 255, 255, 0.1)',
              borderRadius: '10px',
              position: 'relative',
              transition: 'background 0.2s',
              pointerEvents: 'none'
            }}>
              <div style={{
                width: '16px',
                height: '16px',
                background: '#fff',
                borderRadius: '50%',
                position: 'absolute',
                top: '2px',
                left: autonomy ? '22px' : '2px',
                transition: 'left 0.2s'
              }} />
            </div>
            <input
              type="checkbox"
              checked={autonomy}
              onChange={(e) => setAutonomy(e.target.checked)}
              style={{ display: 'none' }}
              disabled
            />
            <span style={{ fontSize: '12px', color: autonomy ? '#e9d8fd' : 'var(--muted-foreground)' }}>
              {autonomy ? 'ENABLED (YELLOW allowed)' : 'DISABLED (GREEN only)'}
            </span>
          </label>
        </div>

        {/* Theme Settings */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <Sliders size={14} style={{ color: 'var(--ag-text-amber)' }} />
            <strong style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>UI Theme</strong>
          </div>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            style={{
              width: '100%',
              padding: '8px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border)',
              color: 'var(--foreground)',
              borderRadius: '4px',
              fontSize: '12px',
              outline: 'none'
            }}
          >
            <option value="Superbrain">Superbrain (3D Hero)</option>
            <option value="Classic">Classic Dashboard</option>
            <option value="Minimal">Minimal Chrome</option>
          </select>
        </div>

        <div style={{ marginTop: 'auto', paddingTop: '16px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button
            disabled={busy}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--danger)',
              fontSize: '12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
            onClick={async () => {
              if (window.confirm('Restart AI-OS Backend? In-flight requests will be dropped.')) {
                setBusy(true);
                try {
                  await postJson('/api/v1/system/restart', { confirm: true });
                  alert('Restart signal sent.');
                } catch (err) {
                  alert('Restart failed: ' + err.message);
                } finally {
                  setBusy(false);
                }
              }
            }}
          >
            <Power size={14} /> Restart Backend
          </button>

          <button
            disabled={busy}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid var(--border)',
              padding: '6px 16px',
              color: '#fff',
              borderRadius: '4px',
              fontSize: '12px',
              cursor: 'pointer'
            }}
            onClick={async () => {
              setBusy(true);
              try {
                await postJson('/api/v1/system/config', { provider, autonomy, theme });
                onClose();
              } catch (err) {
                alert('Save config failed: ' + err.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? 'Saving...' : 'Apply & Close'}
          </button>
        </div>
      </div>
    </HUDPanel>
  );
}
