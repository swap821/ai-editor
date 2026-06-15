import { API_BASE, API_HEADERS } from '../../config';
import { getSessionId } from '../../superbrain/lib/sessionId';
import { useOrganFetch } from '../../lib/useOrganFetch';

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

   Honest states (now via the shared useOrganFetch hook — five truth-states):
   loading on first fetch; a calm EMPTY "no understanding frame yet" placeholder when
   the session has no frame (alignment === null — network OK, backend answered, just
   no frame, distinct from offline); on a network failure keep the last frame and
   show a quiet `· link offline` tag (cold-offline shows the OFFLINE placeholder
   immediately, never "loading forever"); on a 5xx an honest error. NEVER fabricate
   a frame — REAL DATA ONLY.
   ──────────────────────────────────────────────────────────────────────────── */

const LIMIT = 1;

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

// The REAL request — POST { sessionId, limit }. A function so each (re)fetch reads
// the current shared session id (the data flow is UNCHANGED; the hook only adds states).
const intentInit = () => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...API_HEADERS },
  body: JSON.stringify({ sessionId: getSessionId(), limit: LIMIT }),
});

// Read `alignment` verbatim — the latest frame object, or null before any turn.
// A null return → the hook reports phase 'empty' (no frame yet, distinct from
// offline). We never reconstruct or default missing scalar fields.
const mapAlignment = (json) =>
  (json && typeof json.alignment === 'object' ? json.alignment : null);

// Bus matchers: a turn completed (a fresh frame exists), or the link (re)connected.
const INTENT_EVENTS = ['synthesis/SYNTHESIS COMPLETE', 'synthesis/AI-OS LINK ESTABLISHED'];

export default function IntentPort() {
  const { data: frame, phase, hadData } = useOrganFetch(
    `${API_BASE}/api/v1/conversation/session`,
    { events: INTENT_EVENTS, onData: mapAlignment, init: intentInit },
  );

  // LOADING — first fetch in flight (skeletons carry an accessible label).
  if (phase === 'loading') {
    return (
      <section aria-label="Intent frame">
        <p className="organs-port-title">Reasoning · Understanding Frame</p>
        <div className="organs-skel" role="status" aria-label="Loading understanding frame…" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  // OFFLINE, first load (no data ever) — honest cold-offline placeholder (W2-5),
  // NOT a perpetual skeleton.
  if (phase === 'offline' && !hadData) {
    return (
      <section aria-label="Intent frame">
        <p className="organs-port-title">Reasoning · Understanding Frame</p>
        <p className="organs-note organs-note--offline" aria-live="polite">
          INTENT OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  // ERROR — the backend answered with a 5xx (or malformed JSON). Surface it.
  if (phase === 'error' && !hadData) {
    return (
      <section aria-label="Intent frame">
        <p className="organs-port-title">Reasoning · Understanding Frame</p>
        <p className="organs-note organs-note--offline" aria-live="polite">
          INTENT ERROR — the AI-OS returned a server error. Retry shortly.
        </p>
      </section>
    );
  }

  // EMPTY — network succeeded, backend answered, but the session has formed no
  // frame yet (alignment === null). DISTINCT from offline.
  if (phase === 'empty' || frame == null) {
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

  // READY (or keep-last while offline/error after a prior good fetch): a quiet
  // "· link offline" tag when the latest refresh could not reach the link.
  const stale = phase === 'offline' || phase === 'error';
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
        {stale && <span className="organs-stale" aria-live="polite">· link offline</span>}
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
