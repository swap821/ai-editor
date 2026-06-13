import { useState } from 'react';
// The ported adapter's directive pipeline (importable, not edited). Using the
// SAME sendDirective the ported command-bar uses keeps ONE directive pipeline —
// the brain reacts to the turn via the cognition bus exactly as before.
import { sendDirective } from '../superbrain/lib/aiosAdapter';

/* ─── CommandLine ────────────────────────────────────────────────────────────
   The unified directive input for the manufacturing form. The ported .command-bar
   is hidden (its 100vw width escaped the dock); this product element lives in the
   shell DOM at the bottom, so it can never ride a fixed/100vw escape. On submit it
   streams a real supervised turn — the voyaging brain answers on the bus.
   ──────────────────────────────────────────────────────────────────────────── */
export default function CommandLine() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e?.preventDefault();
    const directive = text.trim();
    if (!directive || busy) return;
    setText('');
    setBusy(true);
    try {
      await sendDirective(directive);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="sb-command-line" onSubmit={submit}>
      <span className="sb-cl-prompt">&gt;_</span>
      <input
        className="sb-cl-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Direct the Supermind…"
        disabled={busy}
        spellCheck="false"
        autoComplete="off"
      />
      <button className="sb-cl-exec" type="submit" disabled={!text.trim() || busy}>
        {busy ? 'Working…' : 'Execute'}
      </button>
    </form>
  );
}
