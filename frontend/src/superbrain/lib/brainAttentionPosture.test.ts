import { describe, expect, it } from 'vitest';
import { BRAIN_ATTENTION_POSTURE_DURATION_MS, deriveBrainAttentionPosture } from './brainAttentionPosture';
import type { AttentionTransfer, MaterializedTabKind, MaterializedTabRecord, TabLifecycle } from './tabStore';

function tab(
  id: string,
  kind: MaterializedTabKind,
  originLocal: [number, number, number],
  targetLocal: [number, number, number],
  seatIndex: number | null = kind === 'input' ? null : 2,
  lifecycle: TabLifecycle = 'live',
): MaterializedTabRecord {
  return {
    id,
    kind,
    lifecycle,
    originLocal,
    targetLocal,
    seatIndex,
    content: kind === 'content' ? { code: 'print(1)', language: 'python', filepath: `${id}.py` } : null,
    input: kind === 'input' ? { text: 'build' } : null,
    approval: null,
    bornAt: 0,
    phaseStartedAt: 0,
  };
}

const upper = tab('upper', 'content', [0.04, -1, -0.38], [-0.8, -0.66, 0.76], 2);
const lower = tab('lower', 'content', [0.08, -2.35, -0.34], [1.08, -1.92, 0.82], 5);

function transfer(partial: Partial<AttentionTransfer> = {}): AttentionTransfer {
  return {
    fromId: 'upper',
    toId: 'lower',
    direction: 'forward',
    startedAt: 1000,
    ...partial,
  };
}

describe('brainAttentionPosture', () => {
  it('stays neutral when no workspace can be attended', () => {
    expect(deriveBrainAttentionPosture({ tabs: [], focusId: null, nowMs: 1200 })).toEqual({
      active: false,
      targetId: null,
      intensity: 0,
      yaw: 0,
      pitch: 0,
      roll: 0,
      offsetX: 0,
      offsetY: 0,
      scaleBoost: 0,
    });
  });

  it('holds a resting body aim toward the focused vertebra', () => {
    const posture = deriveBrainAttentionPosture({
      tabs: [upper, lower],
      focusId: 'lower',
      nowMs: 2400,
    });

    expect(posture).toMatchObject({ active: true, targetId: 'lower', intensity: 0.32 });
    expect(posture.yaw).toBeGreaterThan(0);
    expect(posture.pitch).toBeLessThan(0);
    expect(posture.roll).toBeLessThan(0);
    expect(posture.offsetY).toBeLessThan(0);
  });

  it('leans harder toward the destination while attention is transferring', () => {
    const resting = deriveBrainAttentionPosture({
      tabs: [upper, lower],
      focusId: 'lower',
      nowMs: 2400,
    });
    const conducting = deriveBrainAttentionPosture({
      tabs: [upper, lower],
      focusId: 'lower',
      attention: transfer(),
      nowMs: 1000 + BRAIN_ATTENTION_POSTURE_DURATION_MS / 2,
    });

    expect(conducting.targetId).toBe('lower');
    expect(conducting.intensity).toBeGreaterThan(resting.intensity);
    expect(conducting.pitch).toBeLessThan(resting.pitch);
    expect(conducting.scaleBoost).toBeGreaterThan(resting.scaleBoost);
  });

  it('falls back to the live focus after a stale transfer window', () => {
    const posture = deriveBrainAttentionPosture({
      tabs: [upper, lower],
      focusId: 'upper',
      attention: transfer(),
      nowMs: 1000 + BRAIN_ATTENTION_POSTURE_DURATION_MS + 1,
    });

    expect(posture.targetId).toBe('upper');
    expect(posture.intensity).toBe(0.32);
    expect(posture.yaw).toBeLessThan(0);
  });
});
