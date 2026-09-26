import { describe, it, expect } from 'vitest';
import type { OrganismLifecyclePhase } from './organismLifecycle';
import {
  BODY_POSTURES,
  bodyHoldForProjection,
  deriveBodyPosture,
  bodyMotionProfileForPosture,
  postureColor01,
  postureHex,
  postureKeyForPhase,
  lifecyclePhaseForPhysicalProjection,
  type BodyPostureKey,
  type PhysicalBodyProjection,
} from './bodyPosture';

const physical = (overrides: Partial<PhysicalBodyProjection> = {}): PhysicalBodyProjection => ({
  phase: 'resting',
  taskState: 'idle',
  coherence: 'fresh',
  motion: 'calm',
  cortex: { posture: 'rest' },
  verification: { state: 'none' },
  membrane: { state: 'clear' },
  ...overrides,
});

describe('postureHex — single source of truth for status hues (P2.4)', () => {
  it('renders each posture as the sacred tetrad hex', () => {
    expect(postureHex('rest')).toBe('#9e78f5');
    expect(postureHex('think')).toBe('#b06eff');
    expect(postureHex('stream')).toBe('#7bf5fb');
    expect(postureHex('hold')).toBe('#ff7e40');
    expect(postureHex('complete')).toBe('#54f0a0');
    expect(postureHex('unconfirmed')).toBe(postureHex('unverified'));
    expect(postureHex('unverified')).toBe(postureHex('rest'));
    expect(postureHex('error')).toBe('#ff5c48');
    expect(postureHex('stopped')).toBe(postureHex('rest'));
  });
  it('always emits a 7-char #rrggbb (2-digit, zero-padded channels)', () => {
    for (const key of Object.keys(BODY_POSTURES) as BodyPostureKey[]) {
      expect(postureHex(key)).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

describe('bodyPosture — spectral-v1 palette', () => {
  it('keeps the poster "STATUS FROM BODY" tetrad colors exactly', () => {
    expect(BODY_POSTURES.rest.color).toEqual([158, 120, 245]);
    expect(BODY_POSTURES.think.color).toEqual([176, 110, 255]); // poster purple #b06eff
    expect(BODY_POSTURES.stream.color).toEqual([123, 245, 251]); // poster cyan #7bf5fb
    expect(BODY_POSTURES.hold.color).toEqual([255, 126, 64]); // poster orange #ff7e40
    expect(BODY_POSTURES.complete.color).toEqual([84, 240, 160]); // poster green #54f0a0
    expect(BODY_POSTURES.error.color).toEqual([255, 92, 72]);
    expect(BODY_POSTURES.unconfirmed.color).toEqual([158, 120, 245]);
  });

  it('streaming flows fastest, rest slowest', () => {
    expect(BODY_POSTURES.stream.flow).toBeGreaterThan(BODY_POSTURES.think.flow);
    expect(BODY_POSTURES.think.flow).toBeGreaterThan(BODY_POSTURES.rest.flow);
  });

  it('carries the spectral-v1 per-posture tint strength (rest clean → stronger when active)', () => {
    expect(BODY_POSTURES.rest.tint).toBe(0);
    expect(BODY_POSTURES.stream.tint).toBeGreaterThan(BODY_POSTURES.think.tint);
    expect(BODY_POSTURES.error.tint).toBeGreaterThanOrEqual(BODY_POSTURES.stream.tint);
    expect(BODY_POSTURES.rest.tint).toBeLessThan(BODY_POSTURES.complete.tint);
    for (const p of Object.values(BODY_POSTURES)) expect(p.tint).toBeLessThanOrEqual(0.8);
  });
});

describe('bodyMotionProfileForPosture — canonical posture owns metabolic motion', () => {
  it.each([
    ['rest', 1.8, 0, 0],
    ['think', 2.8, 0.048, 0.08],
    ['stream', 4.4, 0.256, 0.56],
    ['hold', 1.2, -0.18, 0.78],
    ['complete', 1.8, 0.024, 0.048],
    ['error', 7.2, 0.198, 0.504],
    ['unverified', 1.8, 0, 0],
    ['unconfirmed', 1.8, 0, 0],
    ['stopped', 1.8, 0, 0],
  ] as const)('%s posture resolves its own pulse and excitation profile', (key, pulseRate, breathGain, rootExcitation) => {
    expect(bodyMotionProfileForPosture(BODY_POSTURES[key])).toEqual({ pulseRate, breathGain, rootExcitation });
  });
});

describe('bodyHoldForProjection — replayed presentation owns the hold boundary', () => {
  it('uses the canonical physical membrane whenever a snapshot is available', () => {
    expect(bodyHoldForProjection(physical({ membrane: { state: 'held' } }), false)).toBe(true);
    expect(bodyHoldForProjection(physical({ membrane: { state: 'clear' } }), true)).toBe(false);
    expect(bodyHoldForProjection(physical({ membrane: { state: 'stopped' } }), true)).toBe(false);
  });

  it('retains the legacy event hold only when no physical projection exists', () => {
    expect(bodyHoldForProjection(null, true)).toBe(true);
    expect(bodyHoldForProjection(undefined, false)).toBe(false);
  });
});

describe('postureKeyForPhase — real lifecycle phases map to postures', () => {
  const cases: Array<[OrganismLifecyclePhase, BodyPostureKey]> = [
    ['booting', 'rest'],
    ['arrival', 'think'],
    ['rest', 'rest'],
    ['attentive', 'think'],
    ['intake', 'think'],
    ['materializing', 'stream'],
    ['working', 'stream'],
    ['conducting', 'stream'],
    ['approval_hold', 'hold'],
    ['error_repair', 'error'],
    ['completion_settle', 'complete'],
    ['reabsorbing', 'complete'],
  ];
  it.each(cases)('phase %s -> posture %s', (phase, key) => {
    expect(postureKeyForPhase(phase)).toBe(key);
  });

  it('falls back to rest for an unknown phase', () => {
    expect(postureKeyForPhase('nonsense' as OrganismLifecyclePhase)).toBe('rest');
  });
});

describe('deriveBodyPosture + postureColor01', () => {
  it('derives the posture object for a phase', () => {
    expect(deriveBodyPosture({ phase: 'conducting' })).toBe(BODY_POSTURES.stream);
    expect(deriveBodyPosture({ phase: 'rest' })).toBe(BODY_POSTURES.rest);
  });

  it('does not use the completion-green posture without explicit verified completion', () => {
    const unverified = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        taskState: 'done-unverified',
        coherence: 'unverified',
        cortex: { posture: 'unverified' },
        verification: { state: 'unverified' },
      }),
    });
    const verified = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        taskState: 'done-verified',
        verification: { state: 'pass' },
      }),
    });

    expect(unverified.key).toBe('unverified');
    expect(unverified.color).toEqual(BODY_POSTURES.rest.color);
    expect(unverified.tint).toBe(0.08);
    expect(verified).toBe(BODY_POSTURES.complete);
  });

  it('projects stale and unavailable snapshots as quiet uncertainty ahead of stale failure receipts', () => {
    const stale = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        phase: 'stale',
        taskState: 'stale',
        coherence: 'stale',
        cortex: { posture: 'recover' },
        verification: { state: 'fail' },
      }),
    });
    const unavailable = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        phase: 'degraded',
        taskState: 'failed',
        coherence: 'degraded',
        cortex: { posture: 'recover' },
        verification: { state: 'fail' },
      }),
    });

    expect(stale).toBe(BODY_POSTURES.unconfirmed);
    expect(unavailable).toBe(BODY_POSTURES.unconfirmed);
    expect(BODY_POSTURES.unconfirmed).toMatchObject({
      color: BODY_POSTURES.rest.color,
      flow: 0.1,
      tint: 0.08,
      label: 'Unconfirmed',
    });
  });

  it('keeps current failure red, while stop and permission retain higher priority', () => {
    const failed = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        phase: 'recovering',
        taskState: 'failed',
        coherence: 'degraded',
        cortex: { posture: 'recover' },
        verification: { state: 'fail' },
      }),
    });
    const refused = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        phase: 'recovering',
        taskState: 'refused',
        coherence: 'degraded',
        cortex: { posture: 'recover' },
        membrane: { state: 'refused' },
      }),
    });
    const permission = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        phase: 'stale',
        taskState: 'needs-permission',
        coherence: 'stale',
        cortex: { posture: 'attention' },
        membrane: { state: 'held' },
      }),
    });
    const stopped = deriveBodyPosture({
      phase: 'rest',
      physical: physical({
        phase: 'stopped',
        taskState: 'stopped',
        coherence: 'stopped',
        cortex: { posture: 'stopped' },
        membrane: { state: 'stopped' },
      }),
    });

    expect(failed).toBe(BODY_POSTURES.error);
    expect(refused).toBe(BODY_POSTURES.error);
    expect(permission).toBe(BODY_POSTURES.hold);
    expect(stopped).toBe(BODY_POSTURES.stopped);
  });

  it('keeps permission, recovery, stop, and arrival mapped to their existing lifecycle gestures', () => {
    expect(lifecyclePhaseForPhysicalProjection(physical({
      taskState: 'needs-permission',
      cortex: { posture: 'attention' },
      membrane: { state: 'held' },
    }))).toBe('approval_hold');
    expect(lifecyclePhaseForPhysicalProjection(physical({
      phase: 'stale',
      taskState: 'stale',
      coherence: 'stale',
      cortex: { posture: 'recover' },
    }))).toBe('rest');
    expect(lifecyclePhaseForPhysicalProjection(physical({
      phase: 'degraded',
      coherence: 'degraded',
      cortex: { posture: 'recover' },
    }))).toBe('rest');
    expect(lifecyclePhaseForPhysicalProjection(physical({
      phase: 'recovering',
      taskState: 'failed',
      coherence: 'degraded',
      cortex: { posture: 'recover' },
      verification: { state: 'fail' },
    }))).toBe('error_repair');
    expect(lifecyclePhaseForPhysicalProjection(physical({
      phase: 'stopped',
      taskState: 'stopped',
      coherence: 'stopped',
      cortex: { posture: 'stopped' },
      membrane: { state: 'stopped' },
    }))).toBe('rest');
    expect(lifecyclePhaseForPhysicalProjection(physical({ phase: 'arriving', cortex: { posture: 'arrive' } }))).toBe('arrival');
  });

  it('normalizes an sRGB triple to 0..1 for Three uniforms', () => {
    expect(postureColor01([255, 0, 51])).toEqual([1, 0, 51 / 255]);
    const [r, g, b] = postureColor01(BODY_POSTURES.stream.color);
    expect(r).toBeCloseTo(123 / 255);
    expect(g).toBeCloseTo(245 / 255);
    expect(b).toBeCloseTo(251 / 255);
  });
});
