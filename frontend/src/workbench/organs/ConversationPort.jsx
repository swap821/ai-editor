import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE, API_HEADERS } from '../../config';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';

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

   Session id is resolved the IDENTICAL way the adapter resolves SESSION_ID (read
   localStorage['aios_session_id']; SSR / no-storage → 'gag-superbrain-hud'). We
   replicate the resolver inline rather than import the module-private constant —
   the zero-touch option that needs no edit to the frozen superbrain adapter.

   Live refresh: re-fetch when the bus reports a turn completed
   ('synthesis' / 'SYNTHESIS COMPLETE') or a (re)connect
   ('synthesis' / 'AI-OS LINK ESTABLISHED'), plus once on mount. A paused/approval
   turn emits no done-synthesis; when the operator approves and the turn finishes,
   that completion fires SYNTHESIS COMPLETE, so the log still refreshes after an
   approval resolves.

   Honest states: loading on first fetch; a calm empty placeholder before the first
   turn; on a failed fetch keep the last-rendered log and show a quiet `· link
   offline` tag (never throw into the render loop, never fabricate a turn).

   Redaction note: the backend scrubs secrets on record (scan_and_redact). Redacted
   spans in an answer are CORRECT and expected, not a defect — we render verbatim
   what episodic returns.
   ──────────────────────────────────────────────────────────────────────────── */

const LIMIT = 100;

/** Resolve the session id EXACTLY as aiosAdapter's SESSION_ID does (shared key). */
function resolveSessionId() {
  if (typeof window === 'undefined') return 'gag-superbrain-hud';
  try {
    return window.localStorage.getItem('aios_session_id') ?? 'gag-superbrain-hud';
  } catch {
    return 'gag-superbrain-hud';
  }
}

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

export default function ConversationPort() {
  // null until first load resolves; [] = a real empty session.
  const [messages, setMessages] = useState(null);
  const [phase, setPhase] = useState('loading'); // loading | live | offline
  // Whether a prior fetch ever succeeded — decides keep-last (offline tag on a
  // populated log) vs the first-load offline placeholder.
  const hadDataRef = useRef(false);
  const endRef = useRef(null);

  const fetchLog = useCallback(async () => {
    const sessionId = resolveSessionId();
    try {
      const r = await fetch(`${API_BASE}/api/v1/conversation/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ sessionId, limit: LIMIT }),
      });
      if (!r.ok) throw new Error(`bad status ${r.status}`);
      const json = await r.json();
      const rows = Array.isArray(json.messages) ? json.messages : [];
      // Map each row to a view bubble: content is [{ text }] chunks, joined
      // verbatim (the full assistant answer — never re-truncated).
      const view = rows
        .filter((row) => row && (row.role === 'user' || row.role === 'assistant'))
        .map((row, i) => ({
          key: i,
          role: row.role,
          text: Array.isArray(row.content)
            ? row.content.map((c) => String(c?.text ?? '')).join('')
            : '',
        }));
      hadDataRef.current = true;
      setMessages(view);
      setPhase('live');
    } catch {
      // Keep the last-rendered log; surface a quiet offline tag. Never throw.
      setPhase('offline');
    }
  }, []);

  useEffect(() => {
    fetchLog();
    const unsub = subscribeCognition((e) => {
      if (!e || e.type !== 'synthesis') return;
      const label = String(e.label || '');
      // A turn completed, or the link (re)connected — re-pull the durable log.
      if (label === 'SYNTHESIS COMPLETE' || label === 'AI-OS LINK ESTABLISHED') {
        void fetchLog();
      }
    });
    return () => unsub();
  }, [fetchLog]);

  // Keep the newest turn in view after a (re)load — newest is last. Guarded:
  // scrollIntoView is absent in some environments (jsdom / older webviews), and a
  // best-effort scroll must NEVER throw into the render loop.
  useEffect(() => {
    const end = endRef.current;
    if (end && typeof end.scrollIntoView === 'function' && messages && messages.length > 0) {
      try {
        end.scrollIntoView({ block: 'nearest' });
      } catch {
        // best-effort only
      }
    }
  }, [messages]);

  // First load, nothing yet → honest loading / offline (never a fabricated turn).
  if (messages === null) {
    return (
      <section aria-label="Conversation log">
        <p className="organs-port-title">Conversation · Session Dialogue</p>
        {phase === 'offline' && !hadDataRef.current ? (
          <p className="organs-note organs-note--offline">
            CONVERSATION OFFLINE — AI-OS unreachable.
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

  return (
    <section aria-label="Conversation log">
      <p className="organs-port-title">
        Conversation · Session Dialogue
        {phase === 'offline' && <span className="organs-stale">· link offline</span>}
      </p>
      {messages.length === 0 ? (
        <p className="organs-note">
          No dialogue yet this session. Speak to the AI-OS from the command bar and
          the exchange records here, verbatim.
        </p>
      ) : (
        <div className="organs-convo">
          {messages.map((m) => (
            <Bubble key={m.key} role={m.role} text={m.text} />
          ))}
          <span ref={endRef} aria-hidden="true" />
        </div>
      )}
    </section>
  );
}
