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
import { sendDirective, sendVoiceTurn, getLastEmittedCode, cancelPendingApproval, getPendingApproval, subscribePendingApproval, previewIntent, fetchOnboardingState, BACKEND_REDACTION_MARKER_RE, transcribeAudio, speakText, setSwarmMode, getSwarmMode, AIOS_BASE } from '../superbrain/lib/aiosAdapter';
import { initSwarmCognitionBridge } from './swarmCognitionBridge';
import ApprovalPanel from '../superbrain/components/ui/ApprovalPanel';
import { publishCognition, subscribeCognition } from '../superbrain/lib/cognitionBus';
import { subscribeSwarmHUD } from '../superbrain/lib/swarmHUDStore';
import { triggerSpineFlash } from './spineFlashBridge';
import { useVoiceSpeak, setVoiceSpeakMuted, setBackendTTS, interruptSpeech } from './voiceSpeak';
import { isWorkIntent } from '../superbrain/lib/intentRouting';
import { deriveCommandDockState } from '../superbrain/lib/commandDockState';
import { useReducedMotion } from '../superbrain/lib/reducedMotion';
import { useTabStore, updateMaterializedTab, getTabStoreSnapshot, focusMaterializedTab } from '../superbrain/lib/tabStore';
import { API_BASE } from '../config';
import { sanitizeToText } from '../utils/sanitizeHtml';
import {
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
} from '../superbrain/lib/activeBrain';
import {
  getConversationPhase,
  setConversationPhase,
  subscribeConversationPhase,
} from '../superbrain/lib/conversationPhaseBus';

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
import SwarmHUD from '../superbrain/components/ui/SwarmHUD';
import CouncilDashboard from './CouncilDashboard';
import OperatorProfileCard from './OperatorProfileCard';
import TrustHalo from './TrustHalo';
import './GagosChrome.css';

const MAX_MESSAGES = 40; // cap the kept history (thread scrolls)
const EXAMPLE_DIRECTIVE = "Try: 'scaffold a FastAPI /health endpoint'";
const HINT_DISMISSED_KEY = 'gagos-onboarding-hint-dismissed';

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
function deriveCoachCards(state) {
  if (!state) return [];
  // First run: lead with WHAT GAGOS IS (the front door's "what is this"), then the
  // safe first action. The identity card drops once they've sent a directive.
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

const LANG_FROM_WORD = {
  python: 'python', py: 'python', javascript: 'javascript', js: 'javascript',
  typescript: 'typescript', ts: 'typescript', bash: 'bash', shell: 'bash', sh: 'bash',
  sql: 'sql', go: 'go', rust: 'rust', html: 'html', css: 'css', json: 'json', c: 'c', cpp: 'cpp',
};
const FILEPATH_FILLER = new Set([
  'a', 'an', 'the', 'please', 'can', 'you', 'me', 'my', 'for', 'to', 'that', 'which', 'with',
  'and', 'of', 'in', 'on', 'file', 'script', 'program', 'code', 'function', 'func', 'def', 'class',
  'method', 'component', 'simple', 'new', 'create', 'write', 'build', 'make', 'implement', 'generate',
  'add', 'fix', 'prints', 'print', 'returns', 'return', 'using', 'use', 'it', 'its', 'named', 'called',
  'do', 'thing', 'some', 'something',
]);

/** Best-effort filename for a materialized work slab. Prefers an explicit filename
 *  in the directive, then a function/identifier name, then a filler-stripped slug;
 *  infers the language from the prose when not given. Exported for tests. */
export function workFilepath(text, language) {
  const raw = String(text || '');
  // 1) explicit filename in the directive wins.
  const explicit = raw.match(/\b([\w-]+\.(?:py|js|jsx|ts|tsx|sh|json|html|css|sql|go|rs|c|cpp|txt|md))\b/i);
  if (explicit) return explicit[1].toLowerCase();
  // 2) infer language from the prose if the caller didn't pass one.
  let lang = language;
  if (!lang) {
    const lw = raw.toLowerCase();
    for (const word of Object.keys(LANG_FROM_WORD)) {
      if (new RegExp(`\\b${word}\\b`).test(lw)) { lang = LANG_FROM_WORD[word]; break; }
    }
  }
  // 3) a declared identifier (function/class/def NAME, or NAME() call) names the file.
  const idMatch = raw.match(/\b(?:function|func|def|class|method|component)\s+([a-z_][\w]*)/i)
    || raw.match(/\b([a-z_][a-z0-9_]{2,})\s*\(/i);
  let slug;
  if (idMatch && !FILEPATH_FILLER.has(idMatch[1].toLowerCase())) {
    slug = idMatch[1].replace(/_/g, '-').toLowerCase();
  } else {
    // 4) cleaner slug — drop verbs/fillers/language words, keep the meaningful nouns.
    slug = raw
      .replace(/[^a-z0-9\s]+/gi, ' ')
      .toLowerCase()
      .split(/\s+/)
      .filter((w) => w && !FILEPATH_FILLER.has(w) && !LANG_FROM_WORD[w])
      .slice(0, 3)
      .join('-') || 'work';
  }
  return `${slug}.${LANG_EXT[lang] || 'txt'}`;
}

/** Pull the code-so-far out of a STREAMING answer (the closing fence may not have
 *  arrived yet) so a work slab can grow live as the reply streams. Returns empty
 *  code until a fence opens. Exported for tests. (Slice 2 / A — live answer stream.) */
export function extractStreamingCode(text) {
  const open = /```([\w+-]*)\n?/.exec(String(text || ''));
  if (!open) return { code: '', language: 'text' };
  const after = String(text).slice(open.index + open[0].length);
  const close = after.indexOf('```');
  const code = close >= 0 ? after.slice(0, close) : after;
  return { code, language: open[1] || 'text' };
}

function formatActiveBrainChip(brain) {
  const model = String(brain.model || '').trim();
  const provider = String(brain.provider || '').trim();
  const privacy = String(brain.privacy || '').trim().toLowerCase();
  const mode = String(brain.mode || '').trim().toLowerCase();
  const name = model || provider || 'auto';
  const meta = [
    model && provider && provider.toLowerCase() !== model.toLowerCase() ? provider : '',
    privacy,
    mode,
  ].filter(Boolean).join(' · ');
  return { name, meta, mode };
}

// Backend redaction markers (secret scanner / privacy filter) arrive as literal
// "[SENSITIVE: <id>]" (and sibling "[... REDACTED]") tokens inside step notes and
// replies. The withheld value never reaches the client — this is presentation
// only: each token renders as a calm chip instead of a raw bracket-hash string.
// Runs AFTER sanitizeToText, building safe React elements (never raw HTML).
// Shared with aiosAdapter's humanizeRedactionMarkers (same source pattern, one
// constant) — split() does not touch the shared /g regex's lastIndex, so this
// is safe to reuse as-is; see the constant's own doc comment for the caveat.
function renderWithRedactionChips(text) {
  const value = String(text ?? '');
  const parts = value.split(BACKEND_REDACTION_MARKER_RE);
  if (parts.length === 1) return value;
  const out = [];
  parts.forEach((part, i) => {
    if (part) out.push(part);
    if (i < parts.length - 1) {
      out.push(
        <span key={`redact-${i}`} className="gagos-redaction" title="Withheld by the security scanner">
          restricted
        </span>,
      );
    }
  });
  return out;
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

function StopIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="5" y1="12" x2="18" y2="12" />
      <polyline points="12 6 18 12 12 18" />
    </svg>
  );
}

function SpeakerIcon({ muted }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
  const [messages, setMessages] = useState([]); // { id, role:'user'|'gagos', text }
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcriptPending, setTranscriptPending] = useState(false);
  const [focused, setFocused] = useState(false); // NeuralCommandDock: input focus → dock engages
  const [voiceSupported] = useState(
    () => typeof window !== 'undefined' && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition),
  );
  const [backendVoice, setBackendVoice] = useState({ stt: false, tts: false });
  const [brainChip, setBrainChip] = useState(() => formatActiveBrainChip(getActiveBrain()));
  // Swarm opt-in: the next directive decomposes across an ephemeral worker
  // colony (backend `swarm: true`). Mirrored into the adapter singleton so
  // approval replays inherit the choice; SEEDED from the singleton so a
  // chrome remount (HMR, error-boundary reset) cannot desync chip vs truth.
  const [swarmOn, setSwarmOn] = useState(() => getSwarmMode());
  const [convPhase, setConvPhase] = useState(() => getConversationPhase());
  const [online, setOnline] = useState(true); // honest backend reachability (polled)
  const [onboarded, setOnboarded] = useState(true); // first-run coach dismissed?
  const [hintDismissed, setHintDismissed] = useState(true); // first-run hint dismissed?
  const [coachStep, setCoachStep] = useState(0);
  const [milestones, setMilestones] = useState(null);
  const [intentHint, setIntentHint] = useState('neutral');
  const [verifyToast, setVerifyToast] = useState(null); // { verdict, detail }
  // The supervised pause, surfaced as a DEPENDABLE DOM gate. The 3D being also
  // presents the approval as a crowned slab, but that path is invisible when the
  // WebGL scene can't render; this gate binds to the same single source of truth
  // (the adapter's pending-approval store) so a YELLOW pause is NEVER left
  // un-actionable. Authoritative decision surface for the supervised loop.
  const [pendingApproval, setPendingApproval] = useState(() => getPendingApproval());
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
  // NeuralCommandDock working-dim: the dock yields while the being orchestrates work
  // (content surfaces present) — unless the operator is actively engaging it.
  const { tabs: liveTabs } = useTabStore();
  const beingWorking = liveTabs.some((t) => t.kind !== 'input' && t.lifecycle !== 'retracting');

  const busyRef = useRef(false);
  const turnTokenRef = useRef(0);
  const abortRef = useRef(null);
  const msgSeqRef = useRef(0);
  const recognitionRef = useRef(null);
  const threadRef = useRef(null);
  const inputRef = useRef(null);
  const workTabIdsRef = useRef([]); // accumulated work tabs (orchestration); newest = center focus
  const writingTabIdRef = useRef(null); // the slab THIS turn is writing into (filled/retracted on resolve)
  const isHoldingMicRef = useRef(false);
  const [micLevel, setMicLevel] = useState(0);
  const analyserCleanupRef = useRef(null);
  const mediaRecorderRef = useRef(null);

  // Live active-LLM line from the router's `route` cognition events.
  useEffect(() => subscribeActiveBrain(() => setBrainChip(formatActiveBrainChip(getActiveBrain()))), []);
  // Bind the DOM approval gate to the persisted pending-approval truth (fires
  // immediately with the current value + on every change). Returns the unsub.
  useEffect(() => subscribePendingApproval(setPendingApproval), []);
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
  useEffect(() => {
    fetch(`${AIOS_BASE}/api/v1/voice/models`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setBackendVoice({ stt: !!d.stt?.enabled, tts: !!d.tts?.enabled });
          setBackendTTS(!!d.tts?.enabled);
        }
      })
      .catch(() => {});
  }, []);
  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'route' && event.data) {
          setActiveBrain({
            provider: event.data.provider,
            model: event.data.model,
            privacy: event.data.privacy,
            turn_id: event.data.turn_id,
            mode: event.data.mode,
          });
        }
      }),
    [],
  );

  // Verify celebration / failure: a transient badge that celebrates a PASS or
  // surfaces a FAIL without parsing tool chatter. Exit is a two-phase timer:
  // after the hold, the toast enters a 'leaving' sub-state (mirrored exit
  // keyframe) for ~250ms before unmounting — reduced-motion skips the delay
  // and unmounts immediately (the delay is JS-timed, not CSS-timed, so a pure
  // `animation: none` override alone would not skip it). Each toast instance
  // is tagged with its own token so a second verify event arriving mid-exit
  // can never have its (newer) toast nulled by the first toast's stale timers.
  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'verify' && event.data?.verdict) {
          const toastToken = {};
          setVerifyToast({ verdict: event.data.verdict, detail: event.detail || '', leaving: false, token: toastToken });
          // PREVIEW (#2): attach the run/verify RESULT to the matching slab so the
          // focused surface shows what the code DID, not just what it says. Match by
          // filename; fall back to the focused content slab when unattributed.
          const verdict = String(event.data.verdict).toLowerCase() === 'pass' ? 'pass' : 'fail';
          const output = String(event.data.output ?? '');
          const targetBase = String(event.data.target ?? '').split(/[\\/]/).pop();
          const snap = getTabStoreSnapshot();
          const match =
            snap.tabs.find(
              (t) => t.kind === 'content' && t.content && t.content.filepath?.split(/[\\/]/).pop() === targetBase,
            ) || snap.tabs.find((t) => t.id === snap.focusId && t.kind === 'content');
          if (match && match.content) {
            updateMaterializedTab(match.id, {
              content: { ...match.content, verifyVerdict: verdict, verifyOutput: output },
            });
          }
          if (reducedMotion) {
            const id = window.setTimeout(() => {
              setVerifyToast((current) => (current?.token === toastToken ? null : current));
            }, 2600);
            return () => window.clearTimeout(id);
          }
          // Timer ids in a closure array (NOT a property on the leave-timer id:
          // setTimeout returns a number in the browser — a Timeout object only
          // in jsdom — so `.unmountId =` throws a strict-mode TypeError live).
          const timers = [];
          timers.push(window.setTimeout(() => {
            setVerifyToast((current) => (current?.token === toastToken ? { ...current, leaving: true } : current));
            timers.push(window.setTimeout(() => {
              setVerifyToast((current) => (current?.token === toastToken ? null : current));
            }, 250));
          }, 2600));
          return () => timers.forEach((t) => window.clearTimeout(t));
        }
      }),
    [reducedMotion],
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

  // First-run coach: only prompt once; localStorage failure silently opts out.
  useEffect(() => {
    try {
      setOnboarded(!!window.localStorage.getItem('gagos-onboarded'));
    } catch {
      setOnboarded(true);
    }
  }, []);

  // First-run hint: only prompt once; localStorage failure silently opts out.
  useEffect(() => {
    try {
      setHintDismissed(!!window.localStorage.getItem(HINT_DISMISSED_KEY));
    } catch {
      setHintDismissed(true);
    }
  }, []);

  // Live onboarding milestones from the backend.
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const state = await fetchOnboardingState();
      if (alive) setMilestones(state);
    };
    void load();
    return () => { alive = false; };
  }, []);

  // The being feels its swarm: bridge colony lifecycle transitions onto the
  // cognition bus (agent-dispatch events, source 'swarm') for the body,
  // terminal, and intake organs. Mounted once for the chrome's lifetime.
  useEffect(() => initSwarmCognitionBridge(), []);

  // First-cloud-route hint: when a subtask is first routed to the cloud factory,
  // fire a one-shot travelling flash down the spine. Guarded by a per-session ref
  // and localStorage so it only celebrates the operator's first cloud route.
  const hasCloudFlashedRef = useRef(false);
  useEffect(() => {
    const unsub = subscribeSwarmHUD((swarm) => {
      if (swarm.cloudIndices.length === 0 || hasCloudFlashedRef.current) return;
      hasCloudFlashedRef.current = true;
      try {
        if (!window.localStorage.getItem('gagos-cloudroute-flash-shown')) {
          triggerSpineFlash();
          window.localStorage.setItem('gagos-cloudroute-flash-shown', '1');
        }
      } catch {
        // storage may be blocked; still visually cue if we can
        triggerSpineFlash();
      }
    });
    return unsub;
  }, []);

  // Backend-driven intent preview: tint the command dock toward the predicted mode.
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
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    // C17 FIX: sanitize user input before rendering in the DOM thread.
    // While user input is less dangerous than LLM output (it's their own text),
    // sanitizing prevents self-XSS if the user pastes malicious content.
    pushMessage('user', sanitizeToText(cleanText(text, 400)));
    // SP1 (voice-into-body, minimal hybrid): the GAGOS chat reply now lives in the
    // BODY as in-scene luminous body-speech (BodySpeech + replyVoiceBus), NOT a DOM
    // bubble. The thread keeps only the user's echo (+ work-materialization notes +
    // errors). gagosId stays null; the error fallback below pushes its own message.
    const gagosId = null;

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
        // C-Slice1 (live writing): materialize a "writing…" skeleton IMMEDIATELY so
        // you watch the being write into its OWN body during the turn, instead of a
        // blank wait. We own this slab by id and fill it (code reveals in) or retract
        // it once the turn resolves — or, for a supervised write, after approval.
        const writeSeat = selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
        const writingTab = showContentSurface(
          { code: '', language: 'text', filepath: workFilepath(text), streaming: true },
          getContentSurfacePlacement(writeSeat),
        );
        workTabIdsRef.current.push(writingTab.id);
        // Cap the orchestration: beyond 5 tabs the OLDEST reabsorbs up the spine (phase 7).
        while (workTabIdsRef.current.length > 5) {
          const oldest = workTabIdsRef.current.shift();
          if (oldest) beginRetractingMaterializedTab(oldest);
        }
        const beforeCode = getLastEmittedCode();
        // Slice 2 (A): grow the owned slab LIVE as the answer streams in (the same
        // word-by-word stream the chat reply uses). Once a code fence opens, the
        // code-so-far reveals into the slab; the final settle (below) cleans it up.
        const onWritingChunk = (answer) => {
          if (turnTokenRef.current !== token) return;
          // Refresh the claim on every chunk -- without this, a turn that runs
          // longer than the claim window (e.g. tool calls/agent dispatch before
          // the final code emission) lets it lapse mid-flight, and the backend's
          // CODE EMITTED auto-fire (MaterializationLayer) treats a genuine event
          // as unclaimed and materializes a duplicate tab for the same turn.
          claimWorkMaterialization();
          const partial = extractStreamingCode(answer);
          if (partial.code && partial.code.trim()) {
            updateMaterializedTab(writingTab.id, {
              content: {
                code: partial.code,
                language: (partial.language || 'text').toLowerCase(),
                filepath: workFilepath(text),
                streaming: true,
              },
            });
          }
        };
        // Candidate 3: the backend now reveals the FINAL code block as growing
        // code_chunk snapshots (emit-time chunking — the model is non-streaming).
        // These land after the prose stream and refine the slab with the real,
        // structured artifact growing line-by-line into the being's body.
        const onWritingCodeChunk = (code, language) => {
          if (turnTokenRef.current !== token) return;
          claimWorkMaterialization(); // see onWritingChunk: keep the claim alive while streaming
          if (!code || !code.trim()) return;
          updateMaterializedTab(writingTab.id, {
            content: {
              code,
              language: (language || 'text').toLowerCase(),
              filepath: workFilepath(text, language),
              streaming: true,
            },
          });
        };
        const result = await sendDirective(
          text,
          abortRef.current?.signal,
          onWritingChunk,
          onWritingCodeChunk,
        );
        if (turnTokenRef.current !== token) {
          releaseWorkMaterialization();
          return;
        }
        if (result?.paused) {
          // Supervised: the write happens AFTER approval. Keep the writing skeleton on
          // the spine ("awaiting approval") and keep ownership through the operator's
          // decision (long re-claim) so the post-approval CODE EMITTED doesn't double-
          // fire. ApprovalPanel.onSettled fills (authorize) or retracts (reject) it.
          writingTabIdRef.current = writingTab.id;
          claimWorkMaterialization(600000);
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
            // A real artifact -> FILL the owned skeleton in place (by id); the existing
            // line-reveal types the code in. Same slab, same seat — no duplicate.
            const filepath =
              (fresh?.filepath ? fresh.filepath.split(/[\\/]/).pop() : '') || workFilepath(text, language);
            // #3 (operate multiple tabs): if the REAL filename matches a DIFFERENT
            // existing slab (the skeleton's guess differed), fold the code into THAT
            // slab and drop the fresh skeleton — a re-edit updates one slab, never a
            // duplicate. (Same-name guesses already reuse via showContentSurface.)
            const base = filepath.split(/[\\/]/).pop();
            const dup = getTabStoreSnapshot().tabs.find(
              (t) =>
                t.kind === 'content' &&
                t.id !== writingTab.id &&
                t.lifecycle !== 'retracting' &&
                t.content?.filepath?.split(/[\\/]/).pop() === base,
            );
            const targetId = dup ? dup.id : writingTab.id;
            if (dup) {
              beginRetractingMaterializedTab(writingTab.id);
              workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writingTab.id);
              focusMaterializedTab(dup.id);
            }
            updateMaterializedTab(targetId, { content: { code, language, filepath, streaming: false } });
            pushMessage('gagos', `↳ I've materialized ${filepath} on the spine.`);
          } else {
            // No code -> the being is CONVERSING (e.g. asking to clarify). Retract the
            // premature writing skeleton so an empty "writing…" slab never lingers.
            beginRetractingMaterializedTab(writingTab.id);
            workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writingTab.id);
            const replyText = cleanText(stripAlignmentPreamble(result?.answer));
            if (replyText) {
              pushMessage('gagos', replyText);
            } else {
              // The work stream completed with neither code nor prose — a partial or
              // malformed SSE turn. Surface a calm fault instead of pretending silence
              // is a meaningful answer.
              pushMessage('gagos', 'COGNITION FAULT: the stream ended before any code or reply arrived.');
              setConversationPhase('error');
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
            }
          }
          releaseWorkMaterialization();
        }
        // If the turn faulted above, the error posture is already set; otherwise
        // the slab's working posture takes the body back to idle.
        if (getConversationPhase() !== 'error') {
          setConversationPhase('idle');
        }
      } else {
        // CHAT: the reply lives in the BODY (BodySpeech reads these voice-speaking
        // events) — the DOM thread no longer duplicates the GAGOS reply. We still
        // publish the reply chunks (BodySpeech's source) + drive the conversation
        // posture; we just don't render a thread bubble for it.
        const reply = await sendVoiceTurn(text, {
          signal: abortRef.current?.signal,
          modelId: chatModelId,
          onChunk: (partial) => {
            if (turnTokenRef.current !== token) return;
            const chunk = cleanText(partial);
            if (chunk) {
              setConversationPhase('streaming');
              publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.82, data: { phase: 'reply', reply: chunk } });
            }
          },
        });
        if (turnTokenRef.current !== token) return;
        if (!reply.trim()) {
          // The stream ended without emitting any text — a partial/malformed SSE
          // turn. Surface it honestly so the operator knows the mind went quiet
          // for a reason, distinct from an offline-submit guard.
          pushMessage('gagos', 'COGNITION FAULT: the stream ended before any reply arrived.');
          setConversationPhase('error');
          publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.4, data: { phase: 'error' } });
          return;
        }
        setConversationPhase('complete');
      }
      setOnline(true); // a completed turn is proof the backend is reachable
      publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0.6, data: { phase: 'reply-complete' } });
    } catch (error) {
      if (turnTokenRef.current !== token) return;
      const isAbort = error instanceof Error && error.name === 'AbortError';
      if (isAbort) {
        // Operator cancelled — no error message; stopTurn already narrated it.
        return;
      }
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
      // Refresh milestone state so the coach advances as the operator uses GAGOS.
      void fetchOnboardingState().then(setMilestones);
      if (turnTokenRef.current === token) {
        busyRef.current = false;
        setBusy(false);
        // Return focus to the intake so the next turn is one keystroke away,
        // whether the turn succeeded or failed.
        inputRef.current?.focus();
      }
    }
  }, [pushMessage, updateMessage, chatModelId]);

  // Voice input: backend STT (MediaRecorder → faster-whisper) when available,
  // otherwise browser-native SpeechRecognition. Graceful when unsupported.
  useEffect(() => {
    if (backendVoice.stt) {
      // Backend STT path — no SpeechRecognition needed.
      recognitionRef.current = null;
      return undefined;
    }
    const SR = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!SR) return undefined;
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = voiceLang;
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
      if (finalText.trim()) {
        setTranscriptPending(true);
        inputRef.current?.focus();
      }
    };
    recognitionRef.current = rec;
    return () => {
      recognitionRef.current = null;
      try { rec.abort(); } catch { /* already closed */ }
    };
  }, [backendVoice.stt, voiceLang]);

  const startMic = useCallback(() => {
    if (busyRef.current || isHoldingMicRef.current) return;
    isHoldingMicRef.current = true;
    setDraft('');
    if (backendVoice.stt) {
      navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        const chunks = [];
        mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
        mr.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: 'audio/webm' });
          setListening(false);
          transcribeAudio(blob, { language: voiceLang })
            .then((r) => { setDraft(r.text); if (r.text.trim()) { setTranscriptPending(true); inputRef.current?.focus(); } })
            .catch(() => setDraft(''));
        };
        mediaRecorderRef.current = mr;
        mr.start();
        setListening(true);
        // Audio level analyser for mic glow intensity
        try {
          const actx = new AudioContext();
          const src = actx.createMediaStreamSource(stream);
          const analyser = actx.createAnalyser();
          analyser.fftSize = 256;
          src.connect(analyser);
          const buf = new Uint8Array(analyser.frequencyBinCount);
          let raf;
          const tick = () => {
            analyser.getByteTimeDomainData(buf);
            let sum = 0;
            for (let i = 0; i < buf.length; i++) {
              const v = (buf[i] - 128) / 128;
              sum += v * v;
            }
            const rms = Math.sqrt(sum / buf.length);
            setMicLevel(Math.min(1, rms * 3));
            raf = requestAnimationFrame(tick);
          };
          raf = requestAnimationFrame(tick);
          analyserCleanupRef.current = () => {
            cancelAnimationFrame(raf);
            try { actx.close(); } catch { /* already closed */ }
            setMicLevel(0);
          };
        } catch { /* AudioContext unavailable — graceful fallback */ }
      }).catch(() => { isHoldingMicRef.current = false; });
    } else {
      try { recognitionRef.current?.start(); } catch { /* already started */ }
    }
  }, [backendVoice.stt, voiceLang]);

  const stopMic = useCallback(() => {
    if (!isHoldingMicRef.current) return;
    isHoldingMicRef.current = false;
    if (analyserCleanupRef.current) {
      analyserCleanupRef.current();
      analyserCleanupRef.current = null;
    }
    if (backendVoice.stt && mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    } else {
      try { recognitionRef.current?.stop(); } catch { /* already stopped */ }
    }
  }, [backendVoice.stt]);

  const canSend = draft.trim().length > 0 && !busy;

  // Client-side stop: the operator can cut off a long reply/work stream.
  // This only cancels the UI update loop; the backend may still finish its turn,
  // but its output is ignored. If an approval slab was showing, it retracts.
  // Focus returns to the intake immediately.
  const stopTurn = useCallback(() => {
    turnTokenRef.current += 1;
    busyRef.current = false;
    setBusy(false);
    setListening(false);
    try { recognitionRef.current?.abort(); } catch { /* already closed */ }
    try { abortRef.current?.abort(); } catch { /* already closed */ }
    releaseWorkMaterialization();
    cancelPendingApproval();
    setConversationPhase('idle');
    publishCognition({ type: 'voice-speaking', source: 'gagos', intensity: 0, data: { phase: 'stopped' } });
    pushMessage('gagos', 'Stopped.');
    inputRef.current?.focus();
  }, [pushMessage]);

  const finishOnboarding = useCallback(() => {
    try { window.localStorage.setItem('gagos-onboarded', '1'); } catch { /* storage may be blocked */ }
    setOnboarded(true);
  }, []);

  const dismissHint = useCallback(() => {
    try { window.localStorage.setItem(HINT_DISMISSED_KEY, '1'); } catch { /* storage may be blocked */ }
    setHintDismissed(true);
  }, []);

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

  // NeuralCommandDock: the input is a control organ — calm at rest, the membrane
  // warms when engaged (focus/typing/voice/sending), and YIELDS (recedes/dims) while
  // the being orchestrates work, unless the operator is actively engaging it.
  const dock = deriveCommandDockState({
    hasText: draft.trim().length > 0,
    focused,
    listening,
    sending: busy,
    working: beingWorking,
    reducedMotion,
  });

  // Single first-run hint: appears after the multi-step coach is dismissed so the
  // two onboarding surfaces never stack on a brand-new operator.
  const showHint = !hintDismissed && onboarded && messages.length === 0 && !busy;
  const showThinkingEcho = busy && (convPhase === 'thinking' || convPhase === 'awakening' || convPhase === 'streaming');

  return (
    <div className="gagos-chrome" aria-label="GAGOS conversation">
      {/* The chat command nerve is now a REAL 3D tube rendered in the scene
          (CommandNerve3D), not this flat DOM SVG — operator: "nerve should be 3D,
          like a live". The 2D CommandDockTether is retired. */}
      <button type="button" className="gagos-skip" onClick={() => inputRef.current?.focus()}>
        Skip to the chat
      </button>
      <div className="gagos-sr-only" role="status" aria-live="polite" aria-atomic="true">{statusAnnouncement}</div>

      {/* SP3 (voice-into-body): the static wordmark lockup is retired — the BEING is
          the identity (product law), and it introduces itself in the first-run greeting
          below ("I'm GAGOS…"). No detached branding chrome. */}

      <header className="gagos-status" aria-label="GAGOS status">
        <span className={`gagos-pill ${online ? 'gagos-pill--model' : 'gagos-pill--offline'}`}>
          <span className={`gagos-dot ${online ? 'gagos-dot--model' : 'gagos-dot--offline'}`} aria-hidden="true" />
          <span className="gagos-pill__copy">
            <span className="gagos-pill__main">{online ? brainChip.name : 'offline'}</span>
            {online && brainChip.meta ? <span className="gagos-pill__meta">{brainChip.meta}</span> : null}
          </span>
        </span>
        {/* SP2 (voice-into-body): the lifecycle STATE pill is retired — the being's
            posture colour/pulse now carries the live phase (status read OFF THE BODY).
            Only the non-body facts remain as a minimal cue: which model, + supervised. */}
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

      {/* The supervised decision surface — a dependable DOM gate that appears
          whenever the mind pauses on a write/command/fetch, even if the 3D scene
          can't render. AUTHORIZE redeems the server-issued capability; REJECT is
          audited. Only these buttons can approve — no prose ever can. */}
      {pendingApproval ? (
        <ApprovalPanel
          pending={pendingApproval}
          onSettled={(outcome) => {
            setPendingApproval(getPendingApproval());
            const writeId = writingTabIdRef.current;
            writingTabIdRef.current = null;
            if (!outcome) return;
            if (outcome.action === 'reject') {
              // Declined: retract the writing skeleton (nothing was written).
              if (writeId) {
                beginRetractingMaterializedTab(writeId);
                workTabIdsRef.current = workTabIdsRef.current.filter((id) => id !== writeId);
              }
              releaseWorkMaterialization();
              pushMessage('gagos', 'Stood down — that action was declined.');
              return;
            }
            // Authorized: for a file write, FILL the owned skeleton with the approved
            // code (the replay just emitted it) so it reveals in place. For a command/
            // browse (no file artifact), retract the skeleton instead of leaving it empty.
            if (writeId) {
              const isFileKind = outcome.kind === 'create' || outcome.kind === 'edit';
              const emittedNow = getLastEmittedCode();
              // The approved artifact lives in the pending approval itself (a create
              // carries the full content; an edit carries the diff) — NOT in a code
              // SSE frame (the replay doesn't emit one). Fall back to lastEmittedCode.
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
            // Narrate the decision in the thread — the 3D layer also shows it, but a
            // DOM line guarantees a visible, accessible "done" confirmation.
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
        {/* Memory trail (not a chat thread): each turn is a luminous node on a
            vertical filament rising from the dock. The newest memory glows brightest
            near the intake; older ones recede UP the spine-side and dissolve into the
            void (--depth drives opacity/scale/blur). No bubbles, no left/right split. */}
        <div className="gagos-thread" ref={threadRef} role="log" aria-label="Conversation with GAGOS" tabIndex={0}>
          {messages.map((m, i) => {
            const depth = messages.length - 1 - i; // 0 = newest (brightest, by the dock)
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
                      {/* C17 FIX: LLM output is sanitized before DOM insertion.
                          Prompt injection can cause the LLM to emit malicious HTML/JS
                          (e.g. <script>alert(document.cookie)</script>). sanitizeToText
                          escapes all HTML entities and strips dangerous content.
                          Apply to ALL LLM output before rendering. */}
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
