// Pure contract: turn the reply-voice signal into what the BodySpeech renderer draws.
// No THREE, no DOM — testable in isolation. Luminance/text only (sacred palette held).
export type BodySpeechPhase = 'idle' | 'streaming' | 'complete' | 'error';

export interface BodySpeechInput {
  text: string;
  phase: BodySpeechPhase;
  sinceMs: number;
  reducedMotion: boolean;
}
export interface BodySpeechOutput {
  visibleText: string;
  glow: number;
  fade: number;
  active: boolean;
}

export const BODY_SPEECH_HOLD_MS = 2600;
export const BODY_SPEECH_FADE_MS = 1400;
export const BODY_SPEECH_MAX_CHARS = 360;

// Real defect (2026-07-05, reproduced live in a real browser via Kimi WebBridge):
// the renderer drives a troika-three-text mesh imperatively (`t.text = ...;
// t.sync()`), fire-and-forget, every frame the text changes. troika's sync() has
// NO error handling anywhere in its async chain (font load + SDF glyph
// generation) — if that chain never settles for any reason (a transient WebGL
// hiccup during first-time glyph-atlas creation is the realistic real-world
// trigger), troika's internal `_isSyncing` flag is left stuck `true` forever.
// Every subsequent `.sync()` call then just silently queues behind the dead one
// — nothing throws, nothing logs, the mesh's glyph geometry is simply never
// (re)built again. The reply becomes permanently invisible for the rest of the
// page's life while the cognition bus itself reports a perfectly healthy
// 'streaming'/'complete' phase with the full reply text the whole time.
// BODY_SPEECH_SYNC_STALL_MS bounds how long we'll trust an in-flight sync before
// treating it as wedged and forcing a fresh attempt (see decideBodySpeechSync).
export const BODY_SPEECH_SYNC_STALL_MS = 1200;

export type BodySpeechSyncAction = 'skip' | 'sync' | 'force-resync';

/** Pure decision for whether BodySpeech's renderer should (re)issue a troika
 *  sync this frame. `pending`/`pendingSinceMs` track whether a previously
 *  issued sync's completion callback has fired yet, and since when it hasn't —
 *  the caller only updates `pendingSinceMs` on the false->true transition, so
 *  it reflects how long the OLDEST unresolved attempt has been outstanding,
 *  not merely the most recent sync() call (text keeps changing every frame
 *  during normal streaming, which must not keep resetting the stall clock). */
export function decideBodySpeechSync(
  visibleText: string,
  lastSyncedText: string,
  pending: boolean,
  pendingSinceMs: number,
  nowMs: number,
): BodySpeechSyncAction {
  if (pending && nowMs - pendingSinceMs > BODY_SPEECH_SYNC_STALL_MS) {
    return 'force-resync';
  }
  if (visibleText !== lastSyncedText) {
    return 'sync';
  }
  return 'skip';
}

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

export function deriveBodySpeech(input: BodySpeechInput): BodySpeechOutput {
  const { text, phase, sinceMs } = input;
  const trimmed = text.length > BODY_SPEECH_MAX_CHARS ? text.slice(text.length - BODY_SPEECH_MAX_CHARS) : text;

  if (phase === 'idle' || (!trimmed && phase !== 'error')) {
    return { visibleText: '', glow: 0, fade: 0, active: false };
  }
  if (phase === 'streaming') {
    return { visibleText: trimmed, glow: 1, fade: 0, active: true };
  }
  const overHold = sinceMs - BODY_SPEECH_HOLD_MS;
  const fade = overHold <= 0 ? 0 : clamp01(overHold / BODY_SPEECH_FADE_MS);
  const active = fade < 1;
  const glow = active ? (1 - fade) * (phase === 'error' ? 0.7 : 0.85) : 0;
  return { visibleText: active ? trimmed : '', glow, fade, active };
}
