import { useState } from 'react';
import { LayoutGrid, X } from 'lucide-react';

/**
 * Reopen affordance for the 7 default-open workbench panels: each one's
 * close button flips its state to false permanently, and there was no
 * menu, button, or shortcut anywhere to bring a closed panel back short of
 * a full page reload. This is that missing affordance.
 */
export default function PanelLauncher({ panels }) {
  const [open, setOpen] = useState(false);
  const closedPanels = panels.filter((p) => !p.isOpen);

  return (
    <div style={{ position: 'fixed', bottom: 16, right: 16, zIndex: 25, pointerEvents: 'auto' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? 'Close panel launcher' : 'Reopen a closed panel'}
        title={open ? 'Close panel launcher' : 'Reopen a closed panel'}
        style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          background: 'var(--ag-surface-base)',
          border: 'var(--hairline)',
          backdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
          WebkitBackdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
          color: 'var(--text-1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
        }}
      >
        {open ? <X size={16} /> : <LayoutGrid size={16} />}
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            right: 0,
            marginBottom: 8,
            background: 'var(--ag-surface-base)',
            border: 'var(--hairline)',
            borderRadius: 'var(--radius-md)',
            backdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
            WebkitBackdropFilter: 'var(--ag-blur-md) var(--ag-saturate)',
            padding: 8,
            minWidth: 180,
            boxShadow: 'var(--elevation-3)',
          }}
        >
          {panels.map((panel) => (
            <label
              key={panel.name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 8px',
                fontSize: 'var(--text-sm)',
                color: 'var(--text-2)',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={panel.isOpen}
                onChange={() => panel.setOpen(!panel.isOpen)}
              />
              {panel.name}
            </label>
          ))}
          {closedPanels.length === 0 && panels.length > 0 && (
            <div style={{ padding: '4px 8px', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              All panels open
            </div>
          )}
        </div>
      )}
    </div>
  );
}
