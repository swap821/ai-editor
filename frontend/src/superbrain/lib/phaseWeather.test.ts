/** B2 — emotional weather distilled from the cognition bus. */
import { beforeEach, describe, expect, it } from 'vitest';
import { publishCognition } from './cognitionBus';
import {
  CALM_WEATHER,
  PHASE_HUES,
  WONDER_CHORD,
  __resetWeatherForTests,
  getWeather,
  hesitationFlinch,
  installWeather,
  phaseHueOf,
  tensionOf,
  weatherFromEvent,
  wonderChordEnvelope,
  type WeatherState,
} from './phaseWeather';

const NOW = 1_000_000;

function calm(): WeatherState {
  return { ...CALM_WEATHER };
}

describe('weatherFromEvent reducer', () => {
  it('adopts the phase from any spine-carrying event', () => {
    const next = weatherFromEvent(calm(), { type: 'route', phase: 'chemotaxis' }, NOW);
    expect(next.phase).toBe('chemotaxis');
    expect(next.updatedAt).toBe(NOW);
  });

  it('captures confidence from alignment dispatch and hesitation events', () => {
    const aligned = weatherFromEvent(
      calm(),
      { type: 'agent-dispatch', phase: 'chemotaxis', data: { confidence: 0.92 } },
      NOW,
    );
    expect(aligned.confidence).toBe(0.92);

    // The backend stamps confidence.gated with the EMOTION phase (its own
    // HESITATION event type), so a hesitation tints the body purple, not
    // reflex orange — the seam the organism conformance test pinned.
    const hesitant = weatherFromEvent(
      aligned,
      { type: 'hesitation', phase: 'emotion', data: { confidence: 0.41 } },
      NOW + 1,
    );
    expect(hesitant.confidence).toBe(0.41);
    expect(hesitant.phase).toBe('emotion');
  });

  it('clamps confidence into [0, 1] and ignores non-numeric values', () => {
    const over = weatherFromEvent(
      calm(),
      { type: 'agent-dispatch', data: { confidence: 1.7 } },
      NOW,
    );
    expect(over.confidence).toBe(1);

    const junk = weatherFromEvent(
      calm(),
      { type: 'agent-dispatch', data: { confidence: 'high' } },
      NOW,
    );
    expect(junk.confidence).toBeNull();
  });

  it('a fresh directive clears the sky', () => {
    const busy: WeatherState = { phase: 'narrative', confidence: 0.4, updatedAt: NOW - 5 };
    const next = weatherFromEvent(busy, { type: 'directive' }, NOW);
    expect(next.phase).toBeNull();
    expect(next.confidence).toBeNull();
  });

  it('returns the SAME object when nothing changes (cheap per-frame bail)', () => {
    const prev: WeatherState = { phase: 'reflex', confidence: 0.8, updatedAt: NOW - 5 };
    const next = weatherFromEvent(prev, { type: 'directive', phase: 'reflex' } as any, NOW);
    expect(next).toBe(prev);
  });
});

describe('tensionOf', () => {
  it('is 0 with no confidence signal and 0 at full confidence', () => {
    expect(tensionOf(calm(), NOW)).toBe(0);
    expect(tensionOf({ phase: null, confidence: 1, updatedAt: NOW }, NOW)).toBe(0);
  });

  it('grows quadratically with doubt', () => {
    const unsure = { phase: null, confidence: 0.4, updatedAt: NOW } as WeatherState;
    expect(tensionOf(unsure, NOW)).toBeCloseTo(0.36, 5);
  });

  it('fades to calm over 30 seconds', () => {
    const unsure = { phase: null, confidence: 0, updatedAt: NOW } as WeatherState;
    expect(tensionOf(unsure, NOW)).toBe(1);
    expect(tensionOf(unsure, NOW + 15_000)).toBeCloseTo(0.5, 5);
    expect(tensionOf(unsure, NOW + 30_000)).toBe(0);
    expect(tensionOf(unsure, NOW + 60_000)).toBe(0);
  });
});

describe('phaseHueOf — the chord', () => {
  it('maps each foundation layer to its sacred tetrad hue', () => {
    expect(phaseHueOf({ phase: 'chemotaxis', confidence: null, updatedAt: 0 })).toBe('#7bf5fb');
    expect(phaseHueOf({ phase: 'reflex', confidence: null, updatedAt: 0 })).toBe('#ff7e40');
    expect(phaseHueOf({ phase: 'emotion', confidence: null, updatedAt: 0 })).toBe('#b06eff');
    expect(phaseHueOf({ phase: 'narrative', confidence: null, updatedAt: 0 })).toBe('#54f0a0');
  });

  it('reserves wonder: no single hue ever leaks from an ordinary turn', () => {
    expect(phaseHueOf({ phase: 'wonder', confidence: null, updatedAt: 0 })).toBeNull();
    expect(phaseHueOf(calm())).toBeNull();
    expect(WONDER_CHORD).toEqual(Object.values(PHASE_HUES));
  });
});

describe('hesitationFlinch — the held-breath envelope (B3)', () => {
  it('peaks softly at onset and decays without oscillation', () => {
    expect(hesitationFlinch(0, false)).toBeCloseTo(0.25, 5);
    expect(hesitationFlinch(0.5, false)).toBeLessThan(hesitationFlinch(0.2, false));
    expect(hesitationFlinch(0.2, false)).toBeLessThan(0.25);
  });

  it('ends by 1.1s and never fires before onset', () => {
    expect(hesitationFlinch(1.1, false)).toBe(0);
    expect(hesitationFlinch(5, false)).toBe(0);
    expect(hesitationFlinch(-0.1, false)).toBe(0);
  });

  it('reduced motion gets one soft linear crossfade', () => {
    expect(hesitationFlinch(0, true)).toBeCloseTo(0.2, 5);
    expect(hesitationFlinch(0.3, true)).toBeCloseTo(0.1, 5);
    expect(hesitationFlinch(0.6, true)).toBe(0);
  });

  it('stays gentler than the error wince ceiling (0.55) at every point', () => {
    for (let t = 0; t <= 1.2; t += 0.05) {
      expect(hesitationFlinch(t, false)).toBeLessThanOrEqual(0.25);
    }
  });
});

describe('wonderChordEnvelope — the reserved chord (B6)', () => {
  it('is dark before waking and attacks to full unison by 0.9s', () => {
    expect(wonderChordEnvelope(-1, false)).toBe(0);
    expect(wonderChordEnvelope(0.9, false)).toBeCloseTo(1, 5);
    expect(wonderChordEnvelope(0.4, false)).toBeGreaterThan(0.5);
  });

  it('rings down to a soft steady glow and holds it forever', () => {
    expect(wonderChordEnvelope(2.8, false)).toBeCloseTo(0.35, 5);
    expect(wonderChordEnvelope(60, false)).toBeCloseTo(0.35, 5);
    expect(wonderChordEnvelope(1.5, false)).toBeGreaterThan(wonderChordEnvelope(2.5, false));
  });

  it('reduced motion crossfades straight to the steady glow', () => {
    expect(wonderChordEnvelope(0.3, true)).toBeCloseTo(0.175, 5);
    expect(wonderChordEnvelope(0.6, true)).toBeCloseTo(0.35, 5);
    expect(wonderChordEnvelope(10, true)).toBeCloseTo(0.35, 5);
  });
});

describe('bus integration', () => {
  beforeEach(() => {
    __resetWeatherForTests();
    installWeather();
  });

  it('live events update the singleton weather', () => {
    publishCognition({ type: 'route', phase: 'chemotaxis', source: 'test' });
    expect(getWeather().phase).toBe('chemotaxis');

    publishCognition({
      type: 'hesitation',
      phase: 'emotion',
      data: { confidence: 0.3 },
      source: 'test',
    });
    expect(getWeather().phase).toBe('emotion');
    expect(getWeather().confidence).toBe(0.3);

    publishCognition({ type: 'directive', source: 'test' });
    expect(getWeather()).toEqual(
      expect.objectContaining({ phase: null, confidence: null }),
    );
  });
});
