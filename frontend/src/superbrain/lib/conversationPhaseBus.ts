/**
 * conversationPhaseBus — the live "the being is in a conversation" signal.
 *
 * The 2D chat (GagosChrome) drives turns that publish `voice-speaking` cognition,
 * but the organism-phase derivation (organismLifecycle.phaseFor) only colours the
 * body for work surfaces / directives — so a pure CHAT turn never shifted the
 * being's posture (it stayed rest-violet). This bus lets the chat declare its
 * conversational posture directly; the scene + point-field read it with PRIORITY
 * over the idle organism phase, so the being visibly comes alive as you talk:
 *   thinking → purple,  streaming → cyan,  complete → green,  error → red.
 *
 * Lazy decay (no timers): `complete` / `error` auto-fall back to `idle` after a
 * short hold, so the being eases back to rest on its own. The scene polls
 * getConversationPhase() each frame (like getOrganismPhase), so no subscription
 * is required for the visual; setters are module-singleton + SSR-safe.
 */
import type { OrganismLifecyclePhase } from './organismLifecycle';

export type ConversationPhase = 'idle' | 'awakening' | 'thinking' | 'streaming' | 'complete' | 'error';

/** How long the terminal beats linger before easing back to rest. */
export const COMPLETE_HOLD_MS = 2800;
export const ERROR_HOLD_MS = 3600;

interface ConversationState {
  phase: ConversationPhase;
  since: number;
}

let state: ConversationState = { phase: 'idle', since: 0 };
const listeners = new Set<() => void>();

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
}

/** The effective phase after lazy decay of the terminal beats. Pure of `now`
 *  so it is testable; the live getter passes performance.now(). */
export function effectiveConversationPhase(s: ConversationState, now: number): ConversationPhase {
  if (s.phase === 'complete' && now - s.since > COMPLETE_HOLD_MS) return 'idle';
  if (s.phase === 'error' && now - s.since > ERROR_HOLD_MS) return 'idle';
  return s.phase;
}

export function getConversationPhase(): ConversationPhase {
  return effectiveConversationPhase(state, nowMs());
}

export function setConversationPhase(phase: ConversationPhase): void {
  state = { phase, since: nowMs() };
  for (const l of listeners) {
    try { l(); } catch { /* one bad listener never breaks the rest */ }
  }
}

export function subscribeConversationPhase(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Map a conversation posture onto the OrganismLifecyclePhase whose spectral-v1
 *  posture (deriveBodyPosture) carries the right colour/flow — so the existing
 *  posture plumbing is reused, no new colour tables. `idle` → null (fall back to
 *  the organism phase). */
export function conversationToOrganismPhase(phase: ConversationPhase): OrganismLifecyclePhase | null {
  switch (phase) {
    case 'awakening':
    case 'thinking':
      return 'attentive'; // think — purple
    case 'streaming':
      return 'working'; // stream — cyan
    case 'complete':
      return 'completion_settle'; // complete — green
    case 'error':
      return 'error_repair'; // error — red
    case 'idle':
    default:
      return null;
  }
}

export function __resetConversationPhaseForTests(): void {
  state = { phase: 'idle', since: 0 };
  listeners.clear();
}
