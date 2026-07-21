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
import {
  getLastEmittedCode,
  cancelPendingApproval,
  getPendingApproval,
  previewIntent,
  fetchOnboardingState,
  BACKEND_REDACTION_MARKER_RE,
  setSwarmMode,
  getSwarmMode,
} from '../superbrain/lib/aiosAdapter';
import { initSwarmCognitionBridge } from './swarmCognitionBridge';
import ApprovalPanel from '../superbrain/components/ui/ApprovalPanel';
import { subscribeSwarmHUD } from '../superbrain/lib/swarmHUDStore';
import { triggerSpineFlash } from './spineFlashBridge';
import { useVoiceSpeak, setVoiceSpeakMuted, interruptSpeech } from './voiceSpeak';
import { deriveCommandDockState } from '../superbrain/lib/commandDockState';
import { useReducedMotion } from '../superbrain/lib/reducedMotion';
import {
  useTabStore,
  updateMaterializedTab,
  beginRetractingMaterializedTab,
  releaseWorkMaterialization,
} from '../superbrain/lib/tabStore';
import { API_BASE } from '../config';
import { sanitizeToText } from '../utils/sanitizeHtml';
import SwarmHUD from '../superbrain/components/ui/SwarmHUD';
import CouncilDashboard from './CouncilDashboard';
import OperatorProfileCard from './OperatorProfileCard';
import TrustHalo from './TrustHalo';
import './GagosChrome.css';

import { useCognitionBus, formatActiveBrainChip } from './hooks/useCognitionBus';
import { useWorkMaterialization, workFilepath, extractStreamingCode } from './hooks/useWorkMaterialization';
import { useVoiceInput } from './hooks/useVoiceInput';

export { workFilepath, extractStreamingCode };

const EXAMPLE_DIRECTIVE = "Try: 'scaffold a FastAPI /health endpoint'";
const HINT_DISMISSED_KEY = 'gagos-onboarding-hint-dismissed';

function deriveCoachCards(state) {
  if (!state) return [];
  if (!state.firstDirective)
    return [
      'GAGOS — a local-first AI that acts only with your approval.',
      'Type a goal and press Enter.',
    ];
  if (!state.firstApproval) return ['I pause for your approval on writes, commands, and fetches.'];
  if (!state.firstVerify) return ['Watch for the green verify badge when a tool passes.'];
  if (!state.firstCloudRoute) return ['Some subtasks burst to the cloud factory — see the spine flash.'];
  if (!state.firstAutonomy) return ['Earned autonomy lets trusted actions run automatically.'];
  return ["You're fully underway. Keep building."];
}

function renderWithRedactionChips(text) {
  const value = String(text ?? '');
  const parts = value.split(BACKEND_REDACTION_MARKER_RE);
  if (parts.length === 1) return value;
  const out = [];
  parts.forEach((part, i) => {
    if (i % 2 === 0) {
      if (part) out.push(part);
    } else {
      out.push(
        <span key={i} className="gagos-redacted-chip" title="Withheld by privacy policy">
          <span className="gagos-redacted-chip__dot" aria-hidden="true" />
          <span className="gagos-redacted-chip__label">redacted</span>
        </span>,
      );
    }
  });
  return out;
}

function SendIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function SpeakerIcon({ muted }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      {muted ? (
        <>
          <line x1="22" y1="9" x2="16" y2="15" />
          <line x1="16" y1="9" x2="22" y2="15" />
        </>
      ) : (
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
      )}
    </svg>
  );
}

export default function GagosChrome() {
  const [focused, setFocused] = useState(false);
  const [voiceSupported] = useState(
    () => typeof window !== 'undefined' && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition),
  );
  const [swarmOn, setSwarmOn] = useState(() => getSwarmMode());
  const [online, setOnline] = useState(true);
  const [onboarded, setOnboarded] = useState(true);
  const [hintDismissed, setHintDismissed] = useState(true);
  const [milestones, setMilestones] = useState(null);
  const [intentHint, setIntentHint] = useState('neutral');

  const voice = useVoiceSpeak();
  const [voiceLang, setVoiceLang] = useState(() => {
    try { return localStorage.getItem('gagos-voice-lang') || 'en-IN'; } catch { return 'en-IN'; }
  });
  const cycleVoiceLang = useCallback(() => {
    setVoiceLang((prev) => {
      const next = prev === 'en-IN' ? 'hi-IN' : 'en-IN';
      try { localStorage.setItem('gagos-voice-lang', next); } catch { /* blocked */ }
      return next;
    });
  }, []);

  const [chatModelId, setChatModelId] = useState(() => {
    try { return localStorage.getItem('gagos-chat-model') || undefined; } catch { return undefined; }
  });
  const cycleChatModel = useCallback(() => {
    setChatModelId((prev) => {
      const next = prev === 'gemini.gemini-2.5-flash' ? undefined : 'gemini.gemini-2.5-flash';
      try {
        if (next) localStorage.setItem('gagos-chat-model', next);
        else localStorage.removeItem('gagos-chat-model');
      } catch { /* blocked */ }
      return next;
    });
  }, []);

  const reducedMotion = useReducedMotion();

  // 1. Cognition Bus custom hook
  const {
    brainChip,
    pendingApproval,
    convPhase,
    verifyToast,
    setPendingApproval,
  } = useCognitionBus(reducedMotion);

  // 2. Work Materialization custom hook
  const {
    messages,
    pushMessage,
    busy,
    draft,
    setDraft,
    stopTurn,
    submit,
    writingTabIdRef,
    workTabIdsRef,
  } = useWorkMaterialization({
    setOnline,
    setMilestones,
    chatModelId,
  });

  const inputRef = useRef(null);
  const threadRef = useRef(null);
  const busyRef = useRef(busy);
  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  // 3. Voice Input custom hook
  const {
    listening,
    micLevel,
    transcriptPending,
    setTranscriptPending,
    startMic,
    stopMic,
    recognitionRef,
  } = useVoiceInput({
    voiceLang,
    busyRef,
    inputRef,
    setDraft,
  });

  const { tabs: liveTabs } = useTabStore();
  const beingWorking = liveTabs.some((t) => t.kind !== 'input' && t.lifecycle !== 'retracting');

  // Keep newest message in view
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // Focus intake on desktop mount
  useEffect(() => {
    const el = inputRef.current;
    if (el && typeof window !== 'undefined' && window.matchMedia('(min-width: 641px)').matches) {
      el.focus();
    }
  }, []);

  // Poll backend /health
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

  // First-run coach flag
  useEffect(() => {
    try {
      setOnboarded(!!window.localStorage.getItem('gagos-onboarded'));
    } catch {
      setOnboarded(true);
    }
  }, []);

  // First-run hint flag
  useEffect(() => {
    try {
      setHintDismissed(!!window.localStorage.getItem(HINT_DISMISSED_KEY));
    } catch {
      setHintDismissed(true);
    }
  }, []);

  // Onboarding milestones
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const state = await fetchOnboardingState();
      if (alive) setMilestones(state);
    };
    void load();
    return () => { alive = false; };
  }, []);

  // Swarm cognition bridge
  useEffect(() => initSwarmCognitionBridge(), []);

  // Spine flash on cloud route
  const hasCloudFlashedRef = useRef(false);
  useEffect(() => {
    return subscribeSwarmHUD((swarm) => {
      if (swarm.cloudIndices.length === 0 || hasCloudFlashedRef.current) return;
      hasCloudFlashedRef.current = true;
      try {
        if (!window.localStorage.getItem('gagos-cloudroute-flash-shown')) {
          triggerSpineFlash();
          window.localStorage.setItem('gagos-cloudroute-flash-shown', '1');
        }
      } catch {
        triggerSpineFlash();
      }
    });
  }, []);

  // Backend intent preview
  useEffect(() => {
    if (!draft.trim()) {
      setIntentHint('neutral');
      return undefined;
    }
    let alive = true;
    const t = window.setTimeout(async () => {
      const result = await previewIntent(draft);
      if (alive) setIntentHint(result.intent);
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [draft]);

  const finishOnboarding = useCallback(() => {
    try { window.localStorage.setItem('gagos-onboarded', '1'); } catch { /* storage blocked */ }
    setOnboarded(true);
  }, []);

  const dismissHint = useCallback(() => {
    try { window.localStorage.setItem(HINT_DISMISSED_KEY, '1'); } catch { /* storage blocked */ }
    setHintDismissed(true);
  }, []);

  const canSend = draft.trim().length > 0 && !busy;

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

  const dock = deriveCommandDockState({
    hasText: draft.trim().length > 0,
    focused,
    listening,
    sending: busy,
    working: beingWorking,
    reducedMotion,
  });

  const showHint = !hintDismissed && onboarded && messages.length === 0 && !busy;
  const showThinkingEcho = busy && (convPhase === 'thinking' || convPhase === 'awakening' || convPhase === 'streaming');

  return (
    <div className="gagos-chrome" aria-label="GAGOS conversation">
      <button type="button" className="gagos-skip" onClick={() => inputRef.current?.focus()}>
        Skip to the chat
      </button>
      <div className="gagos-sr-only" role="status" aria-live="polite" aria-atomic="true">{statusAnnouncement}</div>

      <header className="gagos-status" aria-label="GAGOS status">
        <span className={`gagos-pill ${online ? 'gagos-pill--model' : 'gagos-pill--offline'}`}>
          <span className={`gagos-dot ${online ? 'gagos-dot--model' : 'gagos-dot--offline'}`} aria-hidden="true" />
          <span className="gagos-pill__copy">
            <span className="gagos-pill__main">{online ? brainChip.name : 'offline'}</span>
            {online && brainChip.meta ? <span className="gagos-pill__meta">{brainChip.meta}</span> : null}
          </span>
        </span>
        <span
          className="gagos-pill gagos-pill--supervised"
          aria-label="Supervised: a human approval gate guards risky actions"
        >
          <span className="gagos-dot gagos-dot--supervised" aria-hidden="true" />
          <span className="gagos-pill__main">supervised</span>
        </span>
        {online && brainChip.mode ? (
          <span
            className={`gagos-pill gagos-pill--mode gagos-pill--mode-${brainChip.mode}`}
            aria-label={`Turn mode: ${brainChip.mode}`}
          >
            <span className="gagos-dot gagos-dot--mode" aria-hidden="true" />
            <span className="gagos-pill__main">{brainChip.mode}</span>
          </span>
        ) : null}
      </header>

      {verifyToast ? (
        <div
          className={`gagos-verify-toast gagos-verify-toast--${verifyToast.verdict}${verifyToast.leaving ? ' gagos-verify-toast--leaving' : ''}`}
          role="status"
          aria-live="polite"
        >
          <span className="gagos-verify-toast__dot" aria-hidden="true" />
          {verifyToast.verdict === 'pass' ? 'Verified' : 'Verify failed'}
        </div>
      ) : null}

      <SwarmHUD />
      <CouncilDashboard />
      <OperatorProfileCard />
      <TrustHalo />

      {pendingApproval ? (
        <ApprovalPanel
          pending={pendingApproval}
          onSettled={(outcome) => {
            setPendingApproval(getPendingApproval());
            const writeId = writingTabIdRef.current;
            writingTabIdRef.current = null;
            if (!outcome) return;
            if (outcome.action === 'reject') {
              if (writeId) {
                beginRetractingMaterializedTab(writeId);
                workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writeId);
              }
              releaseWorkMaterialization();
              pushMessage('gagos', 'Stood down — that action was declined.');
              return;
            }
            if (writeId) {
              const isFileKind = outcome.kind === 'create' || outcome.kind === 'edit';
              const emittedNow = getLastEmittedCode();
              const code =
                (outcome.kind === 'create' ? outcome.content : outcome.kind === 'edit' ? (outcome.content || outcome.diff) : '') ||
                (emittedNow && emittedNow.code) ||
                '';
              if (isFileKind && code.trim()) {
                const filepath = outcome.filepath ? outcome.filepath.split(/[\\/]/).pop() : 'file';
                const ext = (filepath.split('.').pop() || '').toLowerCase();
                const language = (emittedNow && emittedNow.language)
                  || (ext === 'py' ? 'python' : ext === 'ts' ? 'typescript' : ext === 'js' ? 'javascript' : ext || 'text');
                updateMaterializedTab(writeId, { content: { code, language, filepath, streaming: false } });
              } else {
                beginRetractingMaterializedTab(writeId);
                workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writeId);
              }
              releaseWorkMaterialization();
            }
            const verb = outcome.kind === 'create' ? 'Created'
              : outcome.kind === 'edit' ? 'Updated'
              : outcome.kind === 'command' ? 'Ran'
              : outcome.kind === 'browse' ? 'Fetched'
              : 'Approved';
            const target = outcome.filepath
              || (outcome.kind === 'command' ? 'the command' : outcome.kind === 'browse' ? 'the page' : 'the change');
            pushMessage('gagos', `↳ ${verb} ${target}.`);
          }}
        />
      ) : null}

      <section className="gagos-chat" aria-label="Conversation">
        {messages.length === 0 && !busy ? (
          <div className="gagos-welcome" role="group" aria-label="Getting started with GAGOS">
            <p className="gagos-welcome__eyebrow">the voyaging mind · listening</p>
            <p className="gagos-welcome__greeting">
              I'm <span className="gagos-welcome__name">GAGOS</span>, a supervised mind that
              remembers. Where shall we begin?
            </p>
            <div className="gagos-starters" role="list" aria-label="Suggested prompts">
              {[
                'What can you help me with?',
                'Summarise this project',
                'Find bugs in my code',
                'Explain how this works',
              ].map((text) => (
                <button
                  key={text}
                  className="gagos-starter"
                  role="listitem"
                  onClick={() => { setDraft(text); inputRef.current?.focus(); }}
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="gagos-thread" ref={threadRef} role="log" aria-label="Conversation with GAGOS" tabIndex={0}>
          {messages.map((m, i) => {
            const depth = messages.length - 1 - i;
            const streaming = m.role === 'gagos' && i === messages.length - 1 && busy && !!m.text;
            return (
              <div
                key={m.id}
                className={`gagos-msg gagos-msg--${m.role}${depth === 0 ? ' is-latest' : ''}`}
                style={{ '--depth': depth }}
              >
                <span className="gagos-sr-only">{m.role === 'gagos' ? 'GAGOS: ' : 'You: '}</span>
                <span className="gagos-msg__node" aria-hidden="true" />
                {m.role === 'gagos' && !m.text
                  ? <span className="gagos-typing"><i /><i /><i /></span>
                  : <span className="gagos-msg__text">
                      {renderWithRedactionChips(sanitizeToText(m.text))}
                      {streaming ? <span className="gagos-caret" aria-hidden="true" /> : null}
                      {m.retry ? (
                        <button type="button" className="gagos-retry" onClick={() => submit(m.retry)} aria-label={`Retry: ${(m.retry || '').slice(0, 40)}`}>
                          Retry
                        </button>
                      ) : null}
                    </span>}
              </div>
            );
          })}
        </div>

        {showThinkingEcho ? (
          <div className="gagos-thinking-echo" aria-hidden="true">
            <span className="gagos-thinking-echo__label">thinking…</span>
            <span className="gagos-typing"><i /><i /><i /></span>
          </div>
        ) : null}

        <div
          className={`gagos-bar intent-${intentHint}${dock.active ? ' is-active' : ''}${dock.minimized ? ' is-minimized' : ''}`}
          style={{ '--dock-intensity': dock.intensity }}
        >
          <span className="gagos-intent" aria-hidden="true">
            {intentHint === 'code' && '</>'}
            {intentHint === 'browse' && '🌐'}
            {intentHint === 'swarm' && '◫'}
            {intentHint === 'command' && '$'}
          </span>
          <input
            ref={inputRef}
            className={`gagos-input${transcriptPending ? ' has-transcript' : ''}`}
            type="text"
            value={draft}
            placeholder={listening ? 'listening…' : showHint ? EXAMPLE_DIRECTIVE : 'talk to GAGOS…'}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onChange={(e) => { setDraft(e.target.value); setTranscriptPending(false); }}
            onAnimationEnd={() => setTranscriptPending(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); setTranscriptPending(false); void submit(draft); }
              else if (e.key === 'Escape') {
                if (listening) { recognitionRef.current?.stop(); }
                else if (draft) { setDraft(''); setTranscriptPending(false); }
                else { inputRef.current?.blur(); }
              }
            }}
            aria-label="Talk to GAGOS"
          />
          {voiceSupported ? (
            <button
              type="button"
              className={`gagos-btn gagos-mic ${listening ? 'is-listening' : ''}`}
              style={{ '--mic-level': micLevel }}
              disabled={busy}
              aria-disabled={busy}
              aria-pressed={listening}
              onPointerDown={(e) => { e.preventDefault(); startMic(); }}
              onPointerUp={(e) => { e.preventDefault(); stopMic(); }}
              onPointerLeave={(e) => { e.preventDefault(); stopMic(); }}
              onKeyDown={(e) => {
                if (e.repeat || busy) return;
                if (e.key === ' ' || e.key === 'Enter') {
                  e.preventDefault();
                  startMic();
                }
              }}
              onKeyUp={(e) => {
                if (e.key === ' ' || e.key === 'Enter') {
                  e.preventDefault();
                  stopMic();
                }
              }}
              aria-label="Hold to speak to GAGOS"
              title="Hold to speak"
            >
              <MicIcon />
            </button>
          ) : null}
          {voice.supported ? (
            <button
              type="button"
              className={`gagos-btn gagos-speaker ${voice.muted ? 'is-muted' : ''} ${voice.speaking ? 'is-speaking' : ''}`}
              onClick={() => {
                if (voice.speaking) interruptSpeech();
                else setVoiceSpeakMuted(!voice.muted);
              }}
              aria-pressed={voice.muted}
              aria-label={voice.speaking ? 'Interrupt speech' : voice.muted ? 'Unmute GAGOS voice' : 'Mute GAGOS voice'}
              title={voice.speaking ? 'Tap to interrupt' : voice.muted ? 'Unmute voice' : 'Mute voice'}
            >
              <SpeakerIcon muted={voice.muted} />
            </button>
          ) : null}
          {voiceSupported ? (
            <button
              type="button"
              className="gagos-btn gagos-lang"
              onClick={cycleVoiceLang}
              aria-label={`Voice language: ${voiceLang === 'en-IN' ? 'English' : 'Hindi'}. Click to switch.`}
              title={voiceLang === 'en-IN' ? 'Switch to Hindi' : 'Switch to English'}
            >
              {voiceLang === 'en-IN' ? 'EN' : 'HI'}
            </button>
          ) : null}
          <button
            type="button"
            className="gagos-btn gagos-model"
            onClick={cycleChatModel}
            aria-label={`Chat model: ${chatModelId ? 'Gemini' : 'Local (Ollama)'}. Click to switch to ${chatModelId ? 'Local (Ollama)' : 'Gemini'}.`}
            title={chatModelId ? 'Switch to Local (Ollama)' : 'Switch to Gemini'}
          >
            {chatModelId ? 'GEMINI' : 'LOCAL'}
          </button>
          <button
            type="button"
            className={`gagos-btn gagos-swarm ${swarmOn ? 'is-on' : ''}`}
            onClick={() => {
              setSwarmOn((prev) => {
                const next = !prev;
                setSwarmMode(next);
                return next;
              });
            }}
            aria-pressed={swarmOn}
            aria-label={
              swarmOn
                ? 'Swarm mode on: directives decompose across an ephemeral worker colony. Click to disable.'
                : 'Swarm mode off. Click to run directives as an ephemeral worker swarm.'
            }
            title={swarmOn ? 'Swarm mode ON' : 'Run as swarm'}
          >
            SWARM
          </button>
          <button
            type="button"
            className={`gagos-btn gagos-send ${busy ? 'is-busy' : ''}`}
            onClick={() => { if (busy) stopTurn(); else void submit(draft); }}
            disabled={!canSend && !busy}
            aria-disabled={!canSend && !busy}
            aria-busy={busy}
            aria-label={busy ? 'Stop' : 'Send'}
          >
            {busy ? <StopIcon /> : <SendIcon />}
          </button>
        </div>

        {messages.length === 0 && !busy ? (
          <>
            {!onboarded ? (
              <div className="gagos-coach" role="dialog" aria-label="Getting started">
                {deriveCoachCards(milestones).map((text, i) => (
                  <div key={i} className="gagos-coach__card">
                    <p>{text}</p>
                  </div>
                ))}
                <div className="gagos-coach__actions">
                  <span />
                  <button type="button" className="gagos-coach__primary" onClick={finishOnboarding}>
                    Got it
                  </button>
                </div>
              </div>
            ) : null}
            {showHint ? (
              <div className="gagos-hint" role="note" aria-label="Onboarding hint">
                <span className="gagos-hint__text">▣ ORGANS · forge (Ctrl+`)</span>
                <button
                  type="button"
                  className="gagos-hint__dismiss"
                  onClick={dismissHint}
                  aria-label="Dismiss onboarding hint"
                  title="Dismiss onboarding hint"
                >
                  ×
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </section>
    </div>
  );
}
