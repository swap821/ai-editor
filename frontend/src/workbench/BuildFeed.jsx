import { useEffect, useState } from 'react';
// The ported cognition bus (importable export, not edited). This is the SAME
// stream the brain narrates on — so the feed is real, never faked.
import { subscribeCognition } from '../superbrain/lib/cognitionBus';

const TYPE_COLOR = {
  'agent-dispatch': '#60a5fa',
  'knowledge-acquired': '#34d399',
  'approval-required': '#fbbf24',
  'approval-resolved': '#a78bfa',
  synthesis: '#818cf8',
};

function colorFor(evt) {
  if (!evt) return 'rgba(160,170,190,0.5)';
  const l = String(evt.label || '');
  if (l.includes('RED') || l.includes('BROKEN') || l.includes('FAULT') || l.includes('OFFLINE') || l.includes('LOST')) {
    return '#f87171';
  }
  return TYPE_COLOR[evt.type] || '#818cf8';
}

/* ─── BuildFeed ──────────────────────────────────────────────────────────────
   The mind narrates its manufacturing here. The voyage band's terminal-log is
   hidden in this form; this re-homes that narration into the forge, where you
   work. Live from the real cognition bus; honest dormancy when idle/offline.
   ──────────────────────────────────────────────────────────────────────────── */
export default function BuildFeed() {
  const [evt, setEvt] = useState(null);

  useEffect(() => {
    return subscribeCognition((e) => {
      if (!e || e.type === 'telemetry') return; // telemetry is data-only, not narration
      setEvt(e);
    });
  }, []);

  const color = colorFor(evt);

  return (
    <div className="sb-buildfeed" aria-live="polite">
      <span className="sb-bf-dot" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
      <span className="sb-bf-label" style={{ color }}>
        {evt ? evt.label : 'AWAITING DIRECTION'}
      </span>
      <span className="sb-bf-detail">
        {evt ? evt.detail : 'direct the mind below — it manufactures here'}
      </span>
    </div>
  );
}
