import { useEffect, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { getSessionId } from '../../superbrain/lib/sessionId';
import { useOrganFetch } from '../../lib/useOrganFetch';

/* ─── CONVERSATION PORT · EPISODIC DIALOGUE LOG ────────────────────────────────
   The full, durable conversation for THIS session — every user prompt and the
   FULL assistant answer, oldest-first, read straight from the brain's L2 episodic
   memory. Read-only.

   Data (the verified PRIMARY path): a real POST /api/v1/conversation/session
   { sessionId, limit:100 } via the product config base/headers. The backend maps
   every persisted turn to { role, content:[{ text }] } with NO truncation — the
   stored answer IS the verbatim streamed answer (main.py joins every text_chunk
   into answer_parts and records it at `done`). Because the session id is the
   SHARED `aios_session_id` localStorage key the canon HUD command bar streams
   through, this log captures EVERY turn — including ones the port never
   originated. That is why the episodic path beats the sendDirective fallback.

   Session id comes from the SINGLE shared resolver (superbrain/lib/sessionId
   getSessionId) — the same read-or-create-persist the adapter and the classic
   shell use, so all four faces stay on one `aios_session_id` and never fork.

   Live refresh: re-fetch when the bus reports a turn completed
   ('synthesis' / 'SYNTHESIS COMPLETE') or a (re)connect
   ('synthesis' / 'AI-OS LINK ESTABLISHED'), plus once on mount. A paused/approval
   turn emits no done-synthesis; when the operator approves and the turn finishes,
   that completion fires SYNTHESIS COMPLETE, so the log still refreshes after an
   approval resolves.

   Honest states (now via the shared useOrganFetch hook — five truth-states):
   loading on first fetch; a calm EMPTY placeholder before the first turn (network
   succeeded, backend answered, zero rows — distinct from offline); on a network
   failure keep the last-rendered log and show a quiet `· link offline` tag
   (cold-offline shows the OFFLINE placeholder immediately, never "loading
   forever"); on a 5xx an honest error with the status code. Never throw into the
   render loop, never fabricate a turn.

   Redaction note: the backend scrubs secrets on record (scan_and_redact). Redacted
   spans in an answer are CORRECT and expected, not a defect — we render verbatim
   what episodic returns.
   ──────────────────────────────────────────────────────────────────────────── */

const LIMIT = 100;

/* ─── Fenced-code splitter ──────────────────────────────────────────────────────
   Split an answer into ordered text / code segments on ```fences```. Same load-
   bearing regex the editor's message renderer uses, so code blocks survive intact
   (language captured, trailing newline trimmed). Whitespace/newlines in both text
   and code are preserved by `white-space: pre-wrap` in organs.css. */
function parseSegments(text) {
  const segments = [];
  const codeRe = /```(\w*)\r?\n?([\s\S]*?)```/g;
  let last = 0;
  let m;
  while ((m = codeRe.exec(text)) !== null) {
    if (m.index > last) {
      segments.push({ type: 'text', content: text.slice(last, m.index) });
    }
    segments.push({ type: 'code', lang: m[1] || '', content: m[2].replace(/\n$/, '') });
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    segments.push({ type: 'text', content: text.slice(last) });
  }
  // An empty answer still yields one (empty) text segment so the bubble renders.
  return segments.length ? segments : [{ type: 'text', content: text }];
}

function CodeBlock({ lang, code }) {
  return (
    <div className="organs-code">
      <div className="organs-code-head">
        <span className="organs-code-lang">{lang || 'code'}</span>
      </div>
      <pre className="organs-code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function Bubble({ role, text }) {
  const isUser = role === 'user';
  const segments = isUser ? null : parseSegments(text);
  return (
    <div className={`organs-msg organs-msg--${isUser ? 'user' : 'assistant'}`}>
      <span className="organs-msg-role">{isUser ? 'YOU' : 'AI-OS'}</span>
      {isUser ? (
        <p className="organs-msg-text">{text}</p>
      ) : (
        <div className="organs-msg-body">
          {segments.map((seg, i) =>
            seg.type === 'code' ? (
              <CodeBlock key={i} lang={seg.lang} code={seg.content} />
            ) : (
              <p className="organs-msg-text" key={i}>
                {seg.content}
              </p>
            )
          )}
        </div>
      )}
    </div>
  );
}

// The REAL request — POST { sessionId, limit }. A function so each (re)fetch reads
// the current shared session id (the data flow is UNCHANGED; the hook only adds states).
const conversationInit = () => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...API_HEADERS },
  body: JSON.stringify({ sessionId: getSessionId(), limit: LIMIT }),
});

// Map the raw response to view bubbles. An empty array → the hook reports phase
// 'empty' (a real, zero-turn session — distinct from offline). Module scope so the
// callback identity is stable across renders.
const mapConversation = (json) => {
  const rows = Array.isArray(json?.messages) ? json.messages : [];
  return rows
    .filter((row) => row && (row.role === 'user' || row.role === 'assistant'))
    .map((row, i) => ({
      key: i,
      role: row.role,
      text: Array.isArray(row.content)
        ? row.content.map((c) => String(c?.text ?? '')).join('')
        : '',
    }));
};

// Bus matchers: a turn completed, or the link (re)connected → re-pull the log.
const CONVERSATION_EVENTS = ['synthesis/SYNTHESIS COMPLETE', 'synthesis/AI-OS LINK ESTABLISHED'];

export default function ConversationPort() {
  const endRef = useRef(null);
  const { data: messages, phase, hadData } = useOrganFetch(
    `${API_BASE}/api/v1/conversation/session`,
    { events: CONVERSATION_EVENTS, onData: mapConversation, init: conversationInit },
  );

  // Keep the newest turn in view after a (re)load — newest is last. Guarded:
  // scrollIntoView is absent in some environments (jsdom / older webviews), and a
  // best-effort scroll must NEVER throw into the render loop.
  useEffect(() => {
    const end = endRef.current;
    if (end && typeof end.scrollIntoView === 'function' && Array.isArray(messages) && messages.length > 0) {
      try {
        end.scrollIntoView({ block: 'nearest' });
      } catch {
        // best-effort only
      }
    }
  }, [messages]);

  // LOADING — first fetch in flight (skeletons carry an accessible label).
  if (phase === 'loading') {
    return (
      <section aria-label="Conversation log">
        <p className="organs-port-title">Conversation · Session Dialogue</p>
        <div className="organs-skel" role="status" aria-label="Loading conversation…" />
        <div className="organs-skel" aria-hidden="true" />
      </section>
    );
  }

  // OFFLINE, first load (no data ever) — honest cold-offline placeholder (W2-5),
  // NOT a perpetual skeleton.
  if (phase === 'offline' && !hadData) {
    return (
      <section aria-label="Conversation log">
        <p className="organs-port-title">Conversation · Session Dialogue</p>
        <p className="organs-note organs-note--offline" aria-live="polite">
          CONVERSATION OFFLINE — AI-OS unreachable.
        </p>
      </section>
    );
  }

  // ERROR — the backend answered with a 5xx (or malformed JSON). Surface it.
  if (phase === 'error' && !hadData) {
    return (
      <section aria-label="Conversation log">
        <p className="organs-port-title">Conversation · Session Dialogue</p>
        <p className="organs-note organs-note--offline" aria-live="polite">
          CONVERSATION ERROR — the AI-OS returned a server error. Retry shortly.
        </p>
      </section>
    );
  }

  // EMPTY — network succeeded, backend answered, but the session has no turns yet.
  // DISTINCT from offline: this is a calm "nothing here", not a link failure.
  if (phase === 'empty') {
    return (
      <section aria-label="Conversation log">
        <p className="organs-port-title">
          Conversation · Session Dialogue
          {phase === 'offline' && <span className="organs-stale">· link offline</span>}
        </p>
        <p className="organs-note">
          No conversation yet this session. Speak to the AI-OS from the command bar and
          the exchange records here, verbatim.
        </p>
      </section>
    );
  }

  // READY (or keep-last while offline/error AFTER a prior good fetch): render the log,
  // with a quiet "· link offline" tag when the latest refresh could not reach the link.
  const rows = Array.isArray(messages) ? messages : [];
  const stale = phase === 'offline' || phase === 'error';
  return (
    <section aria-label="Conversation log">
      <p className="organs-port-title">
        Conversation · Session Dialogue
        {stale && <span className="organs-stale" aria-live="polite">· link offline</span>}
      </p>
      {rows.length === 0 ? (
        <p className="organs-note">
          No conversation yet this session. Speak to the AI-OS from the command bar and
          the exchange records here, verbatim.
        </p>
      ) : (
        <div className="organs-convo">
          {rows.map((m) => (
            <Bubble key={m.key} role={m.role} text={m.text} />
          ))}
          <span ref={endRef} aria-hidden="true" />
        </div>
      )}
    </section>
  );
}
