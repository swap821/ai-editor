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
import { sendDirective, sendVoiceTurn } from '../superbrain/lib/aiosAdapter';
import { publishCognition, subscribeCognition } from '../superbrain/lib/cognitionBus';
import { isWorkIntent } from '../superbrain/lib/intentRouting';
import {
  formatActiveBrainLine,
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
} from '../superbrain/lib/activeBrain';
import './GagosChrome.css';

const MAX_MESSAGES = 40; // cap the kept history (thread scrolls)

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

export default function GagosChrome() {
  const [messages, setMessages] = useState([]); // { id, role:'user'|'gagos', text }
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceSupported] = useState(
    () => typeof window !== 'undefined' && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition),
  );
  const [modelLine, setModelLine] = useState(() => formatActiveBrainLine(getActiveBrain()));

  const busyRef = useRef(false);
  const turnTokenRef = useRef(0);
  const msgSeqRef = useRef(0);
  const recognitionRef = useRef(null);
  const threadRef = useRef(null);

  // Live active-LLM line from the router's `route` cognition events.
  useEffect(() => subscribeActiveBrain(() => setModelLine(formatActiveBrainLine(getActiveBrain()))), []);
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

  const pushMessage = useCallback((role, text) => {
    const id = (msgSeqRef.current += 1);
    setMessages((prev) => [...prev, { id, role, text }].slice(-MAX_MESSAGES));
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
    const gagosId = pushMessage('gagos', '');

    // wake the being — same events the posture machine + scene already react to
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 1, data: { phase: 'question', text } });
    if (workIntent) {
      publishCognition({ type: 'directive', label: text.slice(0, 80), intensity: 1, source: 'gagos' });
    }

    try {
      if (workIntent) {
        const result = await sendDirective(text);
        if (turnTokenRef.current !== token) return;
        const answer = cleanText(result?.answer) || (result?.paused ? 'Holding for your approval.' : '');
        updateMessage(gagosId, answer || 'Done.');
      } else {
        const final = await sendVoiceTurn(text, {
          onChunk: (partial) => {
            if (turnTokenRef.current !== token) return;
            const chunk = cleanText(partial);
            if (chunk) {
              updateMessage(gagosId, chunk);
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.82, data: { phase: 'reply', reply: chunk } });
            }
          },
        });
        if (turnTokenRef.current !== token) return;
        updateMessage(gagosId, cleanText(final) || '…');
      }
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.6, data: { phase: 'reply-complete' } });
    } catch (error) {
      if (turnTokenRef.current !== token) return;
      const detail = error instanceof Error ? error.message : 'link unavailable';
      updateMessage(gagosId, `I could not reach my mind just now (${detail}).`);
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

  const canSend = draft.trim().length > 0 && !busy;

  return (
    <div className="gagos-chrome">
      <div className="gagos-lockup">
        <div className="gagos-wordmark">GAGOS</div>
        <div className="gagos-rule" />
        <div className="gagos-subtitle">the voyaging mind</div>
      </div>

      <div className="gagos-status">
        <span className="gagos-pill">
          <span className="gagos-dot gagos-dot--model" />
          {modelLine}
        </span>
        <span className="gagos-pill gagos-pill--supervised">
          <span className="gagos-dot gagos-dot--supervised" />
          supervised
        </span>
      </div>

      <div className="gagos-chat">
        <div className="gagos-thread" ref={threadRef}>
          {messages.map((m) => (
            <div key={m.id} className={`gagos-msg gagos-msg--${m.role}`}>
              {m.role === 'gagos' && !m.text ? <span className="gagos-typing"><i /><i /><i /></span> : m.text}
            </div>
          ))}
        </div>

        <div className="gagos-bar">
          <input
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
