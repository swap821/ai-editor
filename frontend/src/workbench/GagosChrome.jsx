/**
 * GagosChrome — the crisp 2D product interface layer over the 3D being.
 *
 * Operator-approved pivot (2026-06-20): the earlier "everything is in-world 3D
 * text, no DOM chrome" direction read as floating debug labels. The being stays
 * the diegetic 3D hero on the canvas; identity / live status / the conversation
 * now live in a real, minimal 2D layer so the experience reads as a finished
 * product.
 *
 * Conversation is a left-docked CHAT THREAD (history) + input — docked left so it
 * never overlaps the centered being / spine; newest message sits at the bottom by
 * the input, history scrolls above it.
 *
 * Mounted as a DOM sibling of <WorkspaceCanvas/> (outside the <Canvas>), product
 * only — like BrainstemIntake, this file is NOT mirrored to the lab. It drives
 * turns through the same adapter the being already listens to (sendDirective /
 * sendVoiceTurn) and publishes the same cognition events (directive /
 * voice-speaking) so the 3D being still reacts (posture, glow).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { sendDirective, sendVoiceTurn, getLastEmittedCode } from '../superbrain/lib/aiosAdapter';
import { publishCognition, subscribeCognition } from '../superbrain/lib/cognitionBus';
import { isWorkIntent } from '../superbrain/lib/intentRouting';
import { API_BASE } from '../config';
import {
  formatActiveBrainLine,
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
} from '../superbrain/lib/activeBrain';
import {
  getConversationPhase,
  setConversationPhase,
  subscribeConversationPhase,
} from '../superbrain/lib/conversationPhaseBus';

/** The poster reads STATUS OFF THE BODY (Thinking/Streaming/Complete/Error). The
 *  dot hues mirror the being's spectral-v1 posture colours so the chrome and the
 *  body never disagree (purple think / cyan stream / green complete / red error). */
const PHASE_META = {
  idle: { label: 'resting', color: '#9a7bff' },
  awakening: { label: 'awakening', color: '#b69cff' },
  thinking: { label: 'thinking', color: '#a855f7' },
  streaming: { label: 'streaming', color: '#22d3ee' },
  complete: { label: 'complete', color: '#34d399' },
  error: { label: 'error', color: '#f87171' },
};
import {
  showContentSurface,
  getOccupiedVertebraSeats,
  beginRetractingMaterializedTab,
  claimWorkMaterialization,
  releaseWorkMaterialization,
} from '../superbrain/lib/tabStore';
import {
  getContentSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from '../superbrain/lib/materializedSurfaceAnchors';
import './GagosChrome.css';

const MAX_MESSAGES = 40; // cap the kept history (thread scrolls)

const LANG_EXT = {
  python: 'py', py: 'py', javascript: 'js', js: 'js', jsx: 'jsx', typescript: 'ts',
  ts: 'ts', tsx: 'tsx', bash: 'sh', sh: 'sh', shell: 'sh', json: 'json',
  html: 'html', css: 'css', sql: 'sql', go: 'go', rust: 'rs', c: 'c', cpp: 'cpp', text: 'txt',
};

/** The backend's alignment frame prepends "Unverified assumptions before
 *  proceeding: ..." / "Unresolved but treated as non-blocking: ..." lines (and a
 *  memory-recall step can echo them); strip them so the artifact/reply reads clean. */
function stripAlignmentPreamble(answer) {
  return String(answer ?? '')
    .replace(
      /^(?:\s*(?:Unverified assumptions before proceeding:[^\n]*|Unresolved but treated as non-blocking:[^\n]*)\s*\n?)+/gi,
      '',
    )
    .replace(/^\s+/, '');
}

/** Pull the brain's ACTUAL emitted code out of a work answer. Returns `hasCode`
 *  so the caller can tell a real artifact from a conversational reply — the agent
 *  often asks to clarify instead of writing code, and that is NOT a code tab. */
function extractWork(answer) {
  const raw = stripAlignmentPreamble(answer);
  const fence = raw.match(/```(\w+)?\s*\n([\s\S]*?)```/);
  if (fence) {
    return { code: fence[2].replace(/\s+$/, ''), language: (fence[1] || 'text').toLowerCase(), hasCode: true };
  }
  return { code: '', language: 'text', hasCode: false };
}

/** A friendly slab filename from the request, e.g. "reverse-a-string.py". */
function workFilepath(text, language) {
  const slug = String(text)
    .replace(/^(write|build|create|make|code|implement|fix|add|generate)\b/i, '')
    .replace(/[^a-z0-9]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
    .split('-')
    .filter(Boolean)
    .slice(0, 4)
    .join('-') || 'work';
  return `${slug}.${LANG_EXT[language] || 'txt'}`;
}

function cleanText(text, max = 600) {
  // Strip light markdown so the caption reads as clean prose, not source.
  const compact = String(text ?? '')
    .replace(/\*\*|__|`/g, '')
    .replace(/(^|\s)[*_](\S)/g, '$1$2')
    .replace(/^\s*#{1,6}\s*/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!compact) return '';
  return compact.length > max ? `${compact.slice(0, max - 1)}…` : compact;
}

function MicIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  );
}

function SendIcon({ busy }) {
  if (busy) {
    return (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <path d="M21 12a9 9 0 1 1-6.2-8.6" />
      </svg>
    );
  }
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="5" y1="12" x2="18" y2="12" />
      <polyline points="12 6 18 12 12 18" />
    </svg>
  );
}

function MemoryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="2.6" />
      <path d="M5 12a7 7 0 0 1 7-7" />
      <path d="M19 12a7 7 0 0 1-7 7" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l7 2.6v5.1c0 4.3-3 7-7 8.3-4-1.3-7-4-7-8.3V5.6z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function CodeGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="8 9 5 12 8 15" />
      <polyline points="16 9 19 12 16 15" />
    </svg>
  );
}

/** First-run starter prompts — the being's three superpowers (memory, supervised
 *  safety, materialized work). Clicking PRE-FILLS the intake (never auto-sends —
 *  the operator stays in control); the work prompt then grows a 3D slab. */
const STARTER_PROMPTS = [
  { label: 'What do you remember about this project?', text: 'What do you remember about this project?', Icon: MemoryIcon },
  { label: 'How does your approval gate keep me safe?', text: 'Explain how your supervised approval gate keeps me safe.', Icon: ShieldIcon },
  { label: 'Write a function to reverse a string', text: 'Write a Python function to reverse a string.', Icon: CodeGlyph },
];

export default function GagosChrome() {
  const [messages, setMessages] = useState([]); // { id, role:'user'|'gagos', text }
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceSupported] = useState(
    () => typeof window !== 'undefined' && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition),
  );
  const [modelLine, setModelLine] = useState(() => formatActiveBrainLine(getActiveBrain()));
  const [convPhase, setConvPhase] = useState(() => getConversationPhase());
  const [online, setOnline] = useState(true); // honest backend reachability (polled)

  const busyRef = useRef(false);
  const turnTokenRef = useRef(0);
  const msgSeqRef = useRef(0);
  const recognitionRef = useRef(null);
  const threadRef = useRef(null);
  const inputRef = useRef(null);
  const workTabIdsRef = useRef([]); // accumulated work tabs (orchestration); newest = center focus

  // Live active-LLM line from the router's `route` cognition events.
  useEffect(() => subscribeActiveBrain(() => setModelLine(formatActiveBrainLine(getActiveBrain()))), []);
  // Live state read off the body: subscribe for instant phase changes + a light
  // poll so the lazy decay of complete/error → idle (rest) is reflected too.
  useEffect(() => {
    const sync = () => setConvPhase(getConversationPhase());
    const unsub = subscribeConversationPhase(sync);
    const id = window.setInterval(sync, 500);
    return () => {
      unsub();
      window.clearInterval(id);
    };
  }, []);
  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'route' && event.data) {
          setActiveBrain({
            provider: event.data.provider,
            model: event.data.model,
            privacy: event.data.privacy,
          });
        }
      }),
    [],
  );

  // Keep the newest message in view as the thread grows / streams.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // The intake is ready the instant you arrive — focus it on mount (desktop only,
  // so a phone keyboard never springs up unasked).
  useEffect(() => {
    const el = inputRef.current;
    if (el && typeof window !== 'undefined' && window.matchMedia('(min-width: 641px)').matches) {
      el.focus();
    }
  }, []);

  // Honest connection state: poll the backend /health so the chrome tells you the
  // truth ("offline") instead of pretending GAGOS is reachable. No faked status.
  useEffect(() => {
    let alive = true;
    const ping = async () => {
      const ctrl = new AbortController();
      const to = window.setTimeout(() => ctrl.abort(), 3000);
      try {
        const res = await fetch(`${API_BASE}/health`, { signal: ctrl.signal });
        if (alive) setOnline(res.ok);
      } catch {
        if (alive) setOnline(false);
      } finally {
        window.clearTimeout(to);
      }
    };
    ping();
    const id = window.setInterval(ping, 12000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  const pushMessage = useCallback((role, text, extra) => {
    const id = (msgSeqRef.current += 1);
    setMessages((prev) => [...prev, { id, role, text, ...(extra || {}) }].slice(-MAX_MESSAGES));
    return id;
  }, []);

  const updateMessage = useCallback((id, text) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text } : m)));
  }, []);

  const submit = useCallback(async (raw) => {
    const text = String(raw ?? '').trim();
    if (!text || busyRef.current) return;
    const workIntent = isWorkIntent(text);

    const token = turnTokenRef.current + 1;
    turnTokenRef.current = token;
    busyRef.current = true;
    setBusy(true);
    setDraft('');

    pushMessage('user', cleanText(text, 400));
    // Chat replies stream into a 2D bubble; WORK grows a 3D slab from the being,
    // so a chat bubble is only created for the conversational (non-work) path.
    const gagosId = workIntent ? null : pushMessage('gagos', '');

    // wake the being — same events the posture machine + scene already react to,
    // plus the conversation posture so the body visibly shifts purple→cyan→green.
    setConversationPhase('thinking');
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 1, data: { phase: 'question', text } });
    if (workIntent) {
      publishCognition({ type: 'directive', label: text.slice(0, 80), intensity: 1, source: 'gagos' });
    }

    try {
      if (workIntent) {
        // WORK: the answer materializes as a luminous slab GROWN from a vertebra
        // (poster phase 4). Work tabs ACCUMULATE into the orchestration — the newest
        // becomes the center focus, older ones move to the corners; the OLDEST only
        // reabsorbs up the spine once we exceed the cap (handled after materialize).
        // Own this turn's work materialization so the backend's CODE EMITTED
        // auto-fire (MaterializationLayer) doesn't ALSO spawn a duplicate tab.
        claimWorkMaterialization();
        const beforeCode = getLastEmittedCode();
        const result = await sendDirective(text);
        if (turnTokenRef.current !== token) {
          releaseWorkMaterialization();
          return;
        }
        if (result?.paused) {
          // Approval pause: hand materialization back to the backend flow (it fires
          // CODE EMITTED on approve, which MaterializationLayer then materializes).
          releaseWorkMaterialization();
          pushMessage('gagos', 'Holding for your approval before I build that.');
        } else {
          // Prefer the brain's ACTUAL emitted code (the dedicated `code` SSE frame,
          // captured in the adapter) over the prose `answer` — which carries the
          // reasoning/alignment preamble, not the artifact. Freshness by reference:
          // the adapter swaps this object on every new code frame, so a different
          // ref means THIS turn emitted code (never a stale earlier artifact).
          const emitted = getLastEmittedCode();
          const fresh = emitted && emitted !== beforeCode && emitted.code ? emitted : null;
          const extracted = extractWork(result?.answer);
          const code = fresh ? fresh.code : extracted.code;
          const language = fresh ? (fresh.language || 'text').toLowerCase() : extracted.language;
          const hasCode = Boolean((fresh || extracted.hasCode) && code.trim());
          if (hasCode) {
            // A real artifact -> grow a code tab from a vertebra (poster phase 4-6).
            const filepath =
              (fresh?.filepath ? fresh.filepath.split(/[\\/]/).pop() : '') || workFilepath(text, language);
            const seat = selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
            const tab = showContentSurface({ code, language, filepath }, getContentSurfacePlacement(seat));
            workTabIdsRef.current.push(tab.id);
            // Cap the orchestration: beyond 5 tabs the OLDEST reabsorbs up the spine (phase 7).
            while (workTabIdsRef.current.length > 5) {
              const oldest = workTabIdsRef.current.shift();
              if (oldest) beginRetractingMaterializedTab(oldest);
            }
            pushMessage('gagos', `↳ I've materialized ${filepath} on the spine.`);
          } else {
            // No code -> the being is CONVERSING (e.g. asking to clarify). Show its
            // words as a normal reply; never grow an empty/garbage "code" tab.
            pushMessage('gagos', cleanText(stripAlignmentPreamble(result?.answer)) || '…');
          }
          releaseWorkMaterialization();
        }
        setConversationPhase('idle'); // the slab's working posture takes the body
      } else {
        // CHAT: stream the reply into the 2D thread bubble.
        const final = await sendVoiceTurn(text, {
          onChunk: (partial) => {
            if (turnTokenRef.current !== token) return;
            const chunk = cleanText(partial);
            if (chunk) {
              setConversationPhase('streaming');
              updateMessage(gagosId, chunk);
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.82, data: { phase: 'reply', reply: chunk } });
            }
          },
        });
        if (turnTokenRef.current !== token) return;
        updateMessage(gagosId, cleanText(final) || '…');
        setConversationPhase('complete');
      }
      setOnline(true); // a completed turn is proof the backend is reachable
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.6, data: { phase: 'reply-complete' } });
    } catch (error) {
      if (turnTokenRef.current !== token) return;
      const detail = error instanceof Error ? error.message : 'link unavailable';
      const offline = error instanceof TypeError || /failed to fetch|networkerror|load failed|abort/i.test(detail);
      if (offline) setOnline(false);
      const msg = offline
        ? "I can't reach my backend right now. It may be offline; your words are safe, retry when it's back."
        : `That turn was interrupted (${detail}).`;
      if (gagosId) {
        setMessages((prev) => prev.map((m) => (m.id === gagosId ? { ...m, text: msg, retry: text } : m)));
      } else {
        pushMessage('gagos', msg, { retry: text });
      }
      setConversationPhase('error');
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
    } finally {
      if (turnTokenRef.current === token) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }, [pushMessage, updateMessage]);

  // Web Speech voice input (mic button). Graceful when unsupported.
  useEffect(() => {
    const SR = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!SR) return undefined;
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.onresult = (event) => {
      let finalText = '';
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      setDraft(cleanText(finalText || interim, 200));
      if (finalText.trim()) void submit(finalText);
    };
    recognitionRef.current = rec;
    return () => {
      recognitionRef.current = null;
      try { rec.abort(); } catch { /* already closed */ }
    };
  }, [submit]);

  const toggleMic = useCallback(() => {
    if (busyRef.current) return;
    const rec = recognitionRef.current;
    if (!rec) return;
    if (listening) {
      try { rec.stop(); } catch { /* redundant stop */ }
      return;
    }
    setDraft('');
    try { rec.start(); } catch { /* already started */ }
  }, [listening]);

  const startWith = useCallback((text) => {
    setDraft(text);
    const el = inputRef.current;
    if (el) {
      el.focus();
      try { el.setSelectionRange(text.length, text.length); } catch { /* non-text input */ }
    }
  }, []);

  const canSend = draft.trim().length > 0 && !busy;

  // Screen-reader narration of the being's live state (the visualization is
  // aria-hidden, so the meaning must survive without sight).
  const statusAnnouncement = !online
    ? 'GAGOS is offline'
    : convPhase === 'thinking' || convPhase === 'awakening'
      ? 'GAGOS is thinking'
      : convPhase === 'streaming'
        ? 'GAGOS is replying'
        : convPhase === 'complete'
          ? 'GAGOS replied'
          : convPhase === 'error'
            ? 'GAGOS could not complete that turn'
            : '';

  return (
    <div className="gagos-chrome">
      <button type="button" className="gagos-skip" onClick={() => inputRef.current?.focus()}>
        Skip to the chat
      </button>
      <div className="gagos-sr-only" role="status" aria-live="polite">{statusAnnouncement}</div>

      <div className="gagos-lockup">
        <div className="gagos-wordmark">GAGOS</div>
        <div className="gagos-rule" />
        <div className="gagos-subtitle">the voyaging mind</div>
      </div>

      <div className="gagos-status">
        <span className="gagos-pill">
          <span className={`gagos-dot ${online ? 'gagos-dot--model' : 'gagos-dot--offline'}`} />
          {online ? modelLine : 'offline'}
        </span>
        <span className={`gagos-pill gagos-pill--state ${convPhase !== 'idle' ? 'is-active' : ''}`}>
          <span
            className="gagos-dot"
            style={{
              background: PHASE_META[convPhase].color,
              boxShadow: `0 0 6px ${PHASE_META[convPhase].color}`,
            }}
          />
          {PHASE_META[convPhase].label}
        </span>
        <span className="gagos-pill gagos-pill--supervised">
          <span className="gagos-dot gagos-dot--supervised" />
          supervised
        </span>
      </div>

      <div className="gagos-chat">
        {messages.length === 0 && !busy ? (
          <div className="gagos-welcome" role="group" aria-label="Getting started with GAGOS">
            <p className="gagos-welcome__eyebrow">the voyaging mind · listening</p>
            <p className="gagos-welcome__greeting">
              I'm <span className="gagos-welcome__name">GAGOS</span>, a supervised mind that
              remembers. Where shall we begin?
            </p>
            <div className="gagos-welcome__prompts">
              {STARTER_PROMPTS.map(({ label, text, Icon }) => (
                <button
                  key={label}
                  type="button"
                  className="gagos-starter"
                  onClick={() => startWith(text)}
                >
                  <span className="gagos-starter__icon"><Icon /></span>
                  <span className="gagos-starter__label">{label}</span>
                  <span className="gagos-starter__arrow" aria-hidden="true">→</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
        <div className="gagos-thread" ref={threadRef}>
          {messages.map((m, i) => {
            const streaming = m.role === 'gagos' && i === messages.length - 1 && busy && !!m.text;
            return (
              <div key={m.id} className={`gagos-msg gagos-msg--${m.role}`}>
                {m.role === 'gagos' && !m.text
                  ? <span className="gagos-typing"><i /><i /><i /></span>
                  : <>
                      {m.text}
                      {streaming ? <span className="gagos-caret" aria-hidden="true" /> : null}
                      {m.retry ? (
                        <button type="button" className="gagos-retry" onClick={() => submit(m.retry)}>
                          Retry
                        </button>
                      ) : null}
                    </>}
              </div>
            );
          })}
        </div>

        <div className="gagos-bar">
          <input
            ref={inputRef}
            className="gagos-input"
            type="text"
            value={draft}
            placeholder={listening ? 'listening…' : 'talk to GAGOS…'}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); void submit(draft); }
            }}
            aria-label="Talk to GAGOS"
          />
          {voiceSupported ? (
            <button
              type="button"
              className={`gagos-btn gagos-mic ${listening ? 'is-listening' : ''}`}
              onClick={toggleMic}
              aria-label={listening ? 'Stop listening' : 'Speak to GAGOS'}
              title="Voice"
            >
              <MicIcon />
            </button>
          ) : null}
          <button
            type="button"
            className={`gagos-btn gagos-send ${busy ? 'is-busy' : ''}`}
            onClick={() => void submit(draft)}
            disabled={!canSend && !busy}
            aria-label="Send"
          >
            <SendIcon busy={busy} />
          </button>
        </div>
      </div>
    </div>
  );
}
