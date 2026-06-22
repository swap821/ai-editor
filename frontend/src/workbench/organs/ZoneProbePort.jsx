import { useState, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { truncate } from './_fmt';

/* ─── ZONE PROBE PORT · SECURITY CLASSIFIER ────────────────────────────────────
   A read-only probe into the deterministic security cage: type a command, see the
   GREEN / YELLOW / RED verdict the gateway would assign it — the confidence and
   the human-readable reason. This NEVER executes: /security/classify only
   classifies (it is the cage's observe surface, not its execute surface).

   Data: a real POST /api/v1/security/classify { command } via the product config
   base/headers. REQUEST-DRIVEN only — a probe fires on submit (Enter / button),
   never on a poll or bus event. Offline is per-request: a failed fetch keeps the
   input + the prior verdict and shows an inline offline note, so retry is one
   Enter away.
   ──────────────────────────────────────────────────────────────────────────── */

// zone → row truth-state. GREEN safe (ok); YELLOW caution (busy); RED danger (bad).
const ZONE_CLASS = { GREEN: 'ok', YELLOW: 'busy', RED: 'bad' };

export default function ZoneProbePort() {
  const [command, setCommand] = useState('');
  const [verdict, setVerdict] = useState(null); // null until first probe
  const [phase, setPhase] = useState('idle'); // idle|probing|result|offline
  const [lastCmd, setLastCmd] = useState('');
  const inputRef = useRef(null);

  const runProbe = useCallback(async () => {
    const cmd = command.trim();
    if (!cmd || phase === 'probing') return;
    setPhase('probing');
    setLastCmd(cmd);
    try {
      const r = await fetch(`${API_BASE}/api/v1/security/classify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ command: cmd }),
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      setVerdict(await r.json());
      setPhase('result');
    } catch {
      // Keep the input + any prior verdict; surface an inline offline note.
      setPhase('offline');
    }
  }, [command, phase]);

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      runProbe();
    }
  };

  const zone = verdict?.zone;
  const cls = ZONE_CLASS[zone] ?? '';

  return (
    <section aria-label="Security zone probe">
      <p className="organs-port-title">Security · Zone Probe</p>

      <div className="organs-search">
        <input
          ref={inputRef}
          type="text"
          aria-label="Classify a command's security zone"
          placeholder="Classify a command's zone…"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          type="button"
          onClick={runProbe}
          disabled={phase === 'probing' || !command.trim()}
        >
          {phase === 'probing' ? '…' : 'Classify'}
        </button>
      </div>

      {phase === 'idle' && (
        <p className="organs-note">
          Probe the cage. Type a command to see its deterministic GREEN / YELLOW /
          RED verdict. Read-only — nothing executes.
        </p>
      )}

      {phase === 'probing' && (
        <>
          <div className="organs-skel" aria-hidden="true" />
          <div className="organs-skel" aria-hidden="true" />
        </>
      )}

      {phase === 'offline' && (
        <p className="organs-note organs-note--offline">
          ZONE PROBE OFFLINE — AI-OS unreachable.
        </p>
      )}

      {phase === 'result' && verdict && (
        <div className={`organs-row organs-row--${cls}`} data-zone={zone}>
          <span className={`organs-dot organs-dot--${cls}`} aria-hidden="true" />
          <div className="organs-row-main">
            <div className="organs-row-label">
              <span className="organs-row-name" title={lastCmd}>
                <span className={`organs-zonepill organs-zonepill--${cls}`}>{zone}</span>
                {truncate(lastCmd, 96)}
              </span>
              {zone === 'RED' && (
                <span className="organs-quar" title="RED — danger; the cage refuses to execute this.">
                  RED
                </span>
              )}
            </div>
            <span className="organs-row-eyebrow">
              confidence {(verdict.confidence ?? 0).toFixed(2)}
            </span>
            <span className="organs-rung-prompt" title={verdict.reason}>
              {verdict.reason}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
