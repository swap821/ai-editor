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
