/**
 * GagosChrome — the crisp 2D product interface layer over the 3D being.
 *
 * Operator-approved pivot (2026-06-20): the earlier "everything is in-world 3D
 * text, no DOM chrome" direction read as floating debug labels. The being stays
 * the diegetic 3D hero on the canvas; identity / live status / the conversation
 * now live in a real, minimal 2D layer so the experience reads as a finished
 * product. This deliberately overrides the older PURE-3D law for the chrome only
 * (the being itself is untouched).
 *
 * Mounted as a DOM sibling of <WorkspaceCanvas/> (outside the <Canvas>), product
 * only — like BrainstemIntake, this file is NOT mirrored to the lab.
 *
 * It drives turns through the same adapter the being already listens to
 * (sendDirective / sendVoiceTurn) and publishes the same cognition events
 * (directive / voice-speaking) so the 3D being still reacts (posture, glow).
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

const REPLY_DWELL_MS = 16_000;

function clampText(text, max = 240) {
  // Strip light markdown so the spoken caption reads as clean prose, not source:
  // **bold**/*italic*/__u__ markers, leading #/>, and list bullets.
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
  const [draft, setDraft] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceSupported] = useState(
    () => typeof window !== 'undefined' && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition),
  );
  const [modelLine, setModelLine] = useState(() => formatActiveBrainLine(getActiveBrain()));

  const busyRef = useRef(false);
  const turnTokenRef = useRef(0);
  const recognitionRef = useRef(null);
  const replyTimerRef = useRef(null);

  // Live active-LLM line: the router publishes `route` cognition events; mirror
  // them into the activeBrain store and re-render the model pill.
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

  const showReply = useCallback((text) => {
    const clean = clampText(text);
    if (!clean) return;
    setReply(clean);
    if (replyTimerRef.current) window.clearTimeout(replyTimerRef.current);
    replyTimerRef.current = window.setTimeout(() => {
      if (!busyRef.current) setReply('');
    }, REPLY_DWELL_MS);
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
    setReply('');
    if (replyTimerRef.current) window.clearTimeout(replyTimerRef.current);

    // wake the being — same events the posture machine + scene already react to
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 1, data: { phase: 'question', text } });
    if (workIntent) {
      publishCognition({ type: 'directive', label: text.slice(0, 80), intensity: 1, source: 'gagos' });
    }

    try {
      if (workIntent) {
        const result = await sendDirective(text);
        if (turnTokenRef.current !== token) return;
        if (result?.answer) showReply(result.answer);
        else if (result?.paused) showReply('Holding for your approval.');
      } else {
        const final = await sendVoiceTurn(text, {
          onChunk: (partial) => {
            if (turnTokenRef.current !== token) return;
            const chunk = clampText(partial);
            if (chunk) {
              setReply(chunk);
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.82, data: { phase: 'reply', reply: chunk } });
            }
          },
        });
        if (turnTokenRef.current !== token) return;
        if (final) showReply(final);
      }
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.6, data: { phase: 'reply-complete' } });
    } catch (error) {
      if (turnTokenRef.current !== token) return;
      const detail = error instanceof Error ? error.message : 'link unavailable';
      showReply(`I could not reach my mind just now (${detail}).`);
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
    } finally {
      if (turnTokenRef.current === token) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }, [showReply]);

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
      setDraft(clampText(finalText || interim, 200));
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

  useEffect(() => () => { if (replyTimerRef.current) window.clearTimeout(replyTimerRef.current); }, []);

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

      <div className="gagos-convo">
        <div className={`gagos-reply ${reply ? 'is-visible' : ''}`}>
          {reply ? (
            <>
              <span className="gagos-reply-who">GAGOS</span>
              {reply}
            </>
          ) : null}
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
