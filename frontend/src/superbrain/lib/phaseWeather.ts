/**
 * phaseWeather — the organism's emotional weather, distilled from the bus.
 *
 * B2 of the body-aliveness campaign: the backend's typed event spine stamps a
 * cognitive phase on every frame and the turn's calibrated confidence rides
 * the alignment / hesitation events (B1). This module reduces that stream to
 * ONE tiny state — the active phase + the mind's live confidence — and offers
 * pure helpers the body reads per-frame:
 *
 *   tensionOf(...)  — 0 calm .. 1 unsure; drives point-field micro-jitter
 *   phaseHueOf(...) — the phase chord: each foundation layer owns one sacred
 *                     tetrad hue. WONDER deliberately returns null here — the
 *                     four-hue unison chord is reserved for the wonder phase
 *                     (B6) and must never leak out of an ordinary turn.
 *
 * SSR-safe, deterministic, additive: with no spine fields on the stream the
 * state stays null and every consumer renders the prior look, byte-identical.
 */
import { subscribeCognition, type CognitionEvent } from './cognitionBus';

export type CognitivePhase = 'chemotaxis' | 'reflex' | 'emotion' | 'narrative' | 'wonder';

/** The phase chord — sacred tetrad only; no invented colors (palette canon). */
export const PHASE_HUES: Readonly<Record<Exclude<CognitivePhase, 'wonder'>, string>> = {
  chemotaxis: '#7bf5fb',
  reflex: '#ff7e40',
  emotion: '#b06eff',
  narrative: '#54f0a0',
};

/** Wonder never gets a single hue: it is all four at once, reserved for B6. */
export const WONDER_CHORD: readonly string[] = [
  PHASE_HUES.chemotaxis,
  PHASE_HUES.reflex,
  PHASE_HUES.emotion,
  PHASE_HUES.narrative,
];

export interface WeatherState {
  phase: CognitivePhase | null;
  confidence: number | null;
  updatedAt: number;
}

export const CALM_WEATHER: WeatherState = { phase: null, confidence: null, updatedAt: 0 };

function isPhase(value: unknown): value is CognitivePhase {
  return (
    value === 'chemotaxis' ||
    value === 'reflex' ||
    value === 'emotion' ||
    value === 'narrative' ||
    value === 'wonder'
  );
}

/** Pure reducer: fold one cognition event into the weather. Returns the SAME
 *  object when nothing changed so per-frame readers can cheaply bail. */
export function weatherFromEvent(
  prev: WeatherState,
  event: CognitionEvent,
  now: number,
): WeatherState {
  // A new directive is a fresh turn: the sky clears until the mind declares itself.
  if (event.type === 'directive') return { phase: null, confidence: null, updatedAt: now };
  let next: WeatherState | null = null;
  if (isPhase(event.phase) && event.phase !== prev.phase) {
    next = { ...prev, phase: event.phase, updatedAt: now };
  }
  if (event.type === 'agent-dispatch' || event.type === 'hesitation') {
    const confidence = event.data?.confidence;
    if (typeof confidence === 'number' && Number.isFinite(confidence)) {
      next = {
        ...(next ?? prev),
        confidence: Math.min(1, Math.max(0, confidence)),
        updatedAt: now,
      };
    }
  }
  return next ?? prev;
}

const TENSION_FADE_MS = 30_000;

/** 0 = calm .. 1 = maximally unsure. Quadratic so mild uncertainty stays
 *  subtle; fades to calm over 30s so stale weather never haunts the field. */
export function tensionOf(state: WeatherState, now: number): number {
  if (state.confidence === null) return 0;
  const doubt = Math.min(1, Math.max(0, 1 - state.confidence));
  const freshness = Math.min(1, Math.max(0, 1 - (now - state.updatedAt) / TENSION_FADE_MS));
  return doubt * doubt * freshness;
}

/** The active phase's tetrad hue, or null (no phase yet, or wonder = chord). */
export function phaseHueOf(state: WeatherState): string | null {
  if (!state.phase || state.phase === 'wonder') return null;
  return PHASE_HUES[state.phase];
}

/** B3 — the hesitation beat: ONE slow dim swell, a held breath — deliberately
 *  distinct from the error wince (agitated 22Hz throbs) and the approval
 *  release (bright burst). Pure envelope: seconds since onset → flinch
 *  luminance. Reduced motion gets a single soft linear crossfade. */
export function hesitationFlinch(sinceSeconds: number, reducedMotion: boolean): number {
  if (sinceSeconds < 0) return 0;
  if (reducedMotion) {
    return sinceSeconds < 0.6 ? (1 - sinceSeconds / 0.6) * 0.2 : 0;
  }
  return sinceSeconds < 1.1 ? Math.exp(-sinceSeconds * 2.2) * 0.25 : 0;
}

let state: WeatherState = CALM_WEATHER;
let installed = false;
const listeners = new Set<(next: WeatherState) => void>();

/** Idempotent: wire the weather to the cognition bus. Any consumer may call
 *  it any number of times (per-frame included) — only the first call binds. */
export function installWeather(): void {
  if (installed) return;
  installed = true;
  subscribeCognition((event) => {
    const next = weatherFromEvent(state, event, Date.now());
    if (next === state) return;
    state = next;
    for (const listener of listeners) {
      try {
        listener(state);
      } catch {
        // One faulty listener never severs the rest of the nervous system.
      }
    }
  });
}

export function getWeather(): WeatherState {
  return state;
}

export function subscribeWeather(listener: (next: WeatherState) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function __resetWeatherForTests(): void {
  state = CALM_WEATHER;
}
