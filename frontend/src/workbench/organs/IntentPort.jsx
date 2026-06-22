import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';

/* ─── INTENT PORT · PER-TURN SHARED UNDERSTANDING ──────────────────────────────
   A read-only window into the superbrain's UNDERSTANDING layer: the latest
   advisory `UnderstandingFrame` it formed for THIS session's most recent turn —
   the interpreted intent, the desired outcome, its confidence in that reading,
   the assumptions / unknowns / constraints it is carrying, and the next advisory
   action. This is a REASONING organ: it shows what the brain THINKS you asked
   before it acts, so a misread is visible to you.

   TRUTH-STATE, NEVER AUTHORITY. The frame is deliberately non-authoritative
   (aios/core/alignment.py): it cannot approve tools, change zones, or count as
   evidence. We render it verbatim and read-only — there is no control here that
   could grant the brain anything. When the deterministic communication policy
   resolves the turn to `ask` (communication.ambiguity_action === 'ask'), the
   policy-owned clarifying_question is surfaced PROMINENTLY: the brain is waiting
   on you, and that truth-state must be loud.

   DATA — the SAME endpoint + session-id resolution ConversationPort uses:
   POST /api/v1/conversation/session { sessionId, limit } returns an `alignment`
   field = the latest persisted UnderstandingFrame.as_dict() (or null before any
   turn). Shape (validated server-side, every field bounded + secret-redacted):
     { goal, intent, desired_outcome,
       constraints[], assumptions[], unknowns[], decisions[],
       confidence: 0..1, next_action,
       communication: { mode, ambiguity_action, reasons[], clarifying_question },
       correction:    { active, revision, corrected_fields[], source } }
   We read `alignment` ONLY (not messages); a corrected frame carries
   correction.active so we badge it as operator-corrected.

   Live refresh — the IDENTICAL bus contract ConversationPort listens on: re-fetch
   on 'synthesis' / 'SYNTHESIS COMPLETE' (a turn finished → a new frame exists) and
   on 'synthesis' / 'AI-OS LINK ESTABLISHED' (a (re)connect), plus once on mount.

   Honest states: loading on first fetch; a calm "no alignment yet" placeholder when
   the session has no frame (alignment === null); on a failed fetch keep the last
   frame and show a quiet `· link offline` tag. NEVER fabricate a frame — REAL DATA
   ONLY.
   ──────────────────────────────────────────────────────────────────────────── */

const LIMIT = 1;

/** Resolve the session id EXACTLY as aiosAdapter's SESSION_ID does (shared key). */
function resolveSessionId() {
  if (typeof window === 'undefined') return 'gag-superbrain-hud';
  try {
    return window.localStorage.getItem('aios_session_id') ?? 'gag-superbrain-hud';
  } catch {
    return 'gag-superbrain-hud';
  }
}

/* Intent → a one-line plain-language gloss of the eight allowed advisory intents
   (aios/core/alignment.py _ALLOWED_INTENTS). Derived from the same canonical set;
   an unrecognized value (defensive only — the backend bounds it) falls through to
   the raw label so we never hide what the brain actually reported. */
const INTENT_GLOSS = {
  discuss: 'Explore the request and surface tradeoffs.',
  teach: 'Explain the subject and check understanding.',
  plan: 'Develop a plan before acting.',
  execute: 'Act under existing security and approval gates.',
  review: 'Review the target and report evidence.',
  decide: 'Compare options and record a decision.',
  correct: 'Update the shared understanding.',
  unknown: 'Intent not yet determined.',
};

/** Clamp confidence to 0..1 and render as an integer percent (tabular-nums). */
function pct(confidence) {
  const c = Math.max(0, Math.min(1, Number(confidence) || 0));
  return Math.round(c * 100);
}

/* A labeled list of bounded strings (assumptions / unknowns / constraints /
   decisions). Renders nothing when the list is empty — an empty list is honest
   signal (the brain carried no items), not a row to pad. */
function FrameList({ label, items, tone }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  return (
    <div className="organs-intent-list">
      <p className={`organs-intent-list-label${tone ? ` organs-intent-list-label--${tone}` : ''}`}>
        {label} <span className="organs-intent-list-n">{items.length}</span>
      </p>
      <ul className="organs-intent-items">
        {items.map((it, i) => (
          <li key={i} className="organs-intent-item">
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* Coerce a server list field to an array of clean strings (defensive: the backend
   already bounds + redacts these, but the render must never throw on a surprise). */
function asList(value) {
  if (!Array.isArray(value)) return [];
  return value.map((v) => String(v ?? '')).filter(Boolean);
}

export default function IntentPort() {
  // undefined = not loaded yet; null = loaded, session has no frame; object = frame.
  const [frame, setFrame] = useState(undefined);
  const [phase, setPhase] = useState('loading'); // loading | live | offline
  // Whether a prior fetch ever succeeded — decides keep-last (offline tag on a
  // populated frame) vs the first-load offline placeholder.
  const hadDataRef = useRef(false);

  const fetchFrame = useCallback(async () => {
    const sessionId = resolveSessionId();
    try {
      const r = await fetch(`${API_BASE}/api/v1/conversation/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ sessionId, limit: LIMIT }),
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      // `alignment` is the latest frame, or null before any turn. We read it
      // verbatim — never reconstruct or default missing scalar fields.
      const a = json && typeof json.alignment === 'object' ? json.alignment : null;
      hadDataRef.current = true;
      setFrame(a);
      setPhase('live');
    } catch {
      // Keep the last-rendered frame; surface a quiet offline tag. Never throw.
      setPhase('offline');
    }
  }, []);

  useEffect(() => {
    fetchFrame();
    const unsub = subscribeCognition((e) => {
      if (!e || e.type !== 'synthesis') return;
      const label = String(e.label || '');
      // A turn completed (a fresh frame exists), or the link (re)connected.
      if (label === 'SYNTHESIS COMPLETE' || label === 'AI-OS LINK ESTABLISHED') {
        void fetchFrame();
      }
    });
    return () => unsub();
  }, [fetchFrame]);

  // First load, nothing yet → honest loading / offline (never a fabricated frame).
  if (frame === undefined) {
    return (
      <section aria-label="Intent frame">
        <p className="organs-port-title">Reasoning · Understanding Frame</p>
        {phase === 'offline' && !hadDataRef.current ? (
          <p className="organs-note organs-note--offline">
            INTENT OFFLINE — AI-OS unreachable.
          </p>
        ) : (
          <>
            <div className="organs-skel" aria-hidden="true" />
            <div className="organs-skel" aria-hidden="true" />
          </>
        )}
      </section>
    );
  }

  // Loaded, but the session has formed no frame yet (alignment === null).
  if (frame === null) {
    return (
      <section aria-label="Intent frame">
        <p className="organs-port-title">
          Reasoning · Understanding Frame
          {phase === 'offline' && <span className="organs-stale">· link offline</span>}
        </p>
        <p className="organs-note">
          No understanding frame yet this session. Speak to the AI-OS and its
          interpretation of your latest turn appears here — read-only.
        </p>
      </section>
    );
  }

  const intent = String(frame.intent || 'unknown');
  const gloss = INTENT_GLOSS[intent] || '';
  const confidencePct = pct(frame.confidence);
  const comm = (frame.communication && typeof frame.communication === 'object')
    ? frame.communication
    : {};
  const ambiguity = String(comm.ambiguity_action || '');
  const asking = ambiguity === 'ask';
  const clarifying = String(comm.clarifying_question || '');
  const correction = (frame.correction && typeof frame.correction === 'object')
    ? frame.correction
    : {};
  const corrected = Boolean(correction.active);

  return (
    <section aria-label="Intent frame">
      <p className="organs-port-title">
        Reasoning · Understanding Frame
        {phase === 'offline' && <span className="organs-stale">· link offline</span>}
      </p>

      {/* CLARIFYING QUESTION — the loudest truth-state. When the deterministic
          policy resolves to `ask`, the brain is WAITING on the operator; surface
          the policy-owned question prominently above everything else. */}
      {asking && clarifying && (
        <div className="organs-intent-ask" role="status">
          <p className="organs-intent-ask-label">CLARIFICATION NEEDED</p>
          <p className="organs-intent-ask-q">{clarifying}</p>
        </div>
      )}

      {/* Interpreted intent + the confidence meter (read-only, tabular-nums). */}
      <div className="organs-intent-head">
        <div className="organs-intent-head-top">
          <span className="organs-intent-intent">{intent.toUpperCase()}</span>
          {corrected && (
            <span className="organs-intent-corrected" title="Operator-corrected interpretation">
              CORRECTED
            </span>
          )}
        </div>
        {gloss && <p className="organs-intent-gloss">{gloss}</p>}
      </div>

      <div className="organs-intent-meter">
        <div className="organs-intent-meter-row">
          <span className="organs-intent-meter-label">INTERPRETATION CONFIDENCE</span>
          <span className="organs-intent-meter-val">{confidencePct}%</span>
        </div>
        <div className="organs-intent-meter-track" aria-hidden="true">
          <span
            className="organs-intent-meter-fill"
            style={{ transform: `scaleX(${confidencePct / 100})` }}
          />
        </div>
      </div>

      {/* The interpreted goal + desired outcome — the core of the reading. */}
      {frame.goal && (
        <div className="organs-intent-field">
          <p className="organs-intent-field-label">GOAL</p>
          <p className="organs-intent-field-text">{String(frame.goal)}</p>
        </div>
      )}
      {frame.desired_outcome && (
        <div className="organs-intent-field">
          <p className="organs-intent-field-label">DESIRED OUTCOME</p>
          <p className="organs-intent-field-text">{String(frame.desired_outcome)}</p>
        </div>
      )}

      {/* Labeled lists — each renders only when the brain actually carried items. */}
      <FrameList label="ASSUMPTIONS" items={asList(frame.assumptions)} tone="warn" />
      <FrameList label="UNKNOWNS" items={asList(frame.unknowns)} tone="warn" />
      <FrameList label="CONSTRAINTS" items={asList(frame.constraints)} />
      <FrameList label="DECISIONS" items={asList(frame.decisions)} tone="ok" />

      {/* The next advisory action (not authority — the brain's stated next step). */}
      {frame.next_action && (
        <div className="organs-intent-field organs-intent-next">
          <p className="organs-intent-field-label">NEXT ACTION</p>
          <p className="organs-intent-field-text">{String(frame.next_action)}</p>
        </div>
      )}
    </section>
  );
}
