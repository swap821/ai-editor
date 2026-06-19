import { describe, expect, it } from 'vitest';
import { deriveVertebraConductorRoots } from './vertebraConductorRoots';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

const workingMetabolism: TurnMetabolismSnapshot = {
  phase: 'working',
  intensity: 1,
  surfaceExcitation: 0.55,
  rootExcitation: 0.7,
  breathGain: 0.32,
  tint: '#ffbe78',
  held: false,
  changedAt: 1000,
};

const scarImprint: OutcomeImprintSnapshot = {
  kind: 'scar',
  intensity: 1,
  ringOpacity: 0.18,
  scarOpacity: 0.52,
  rootGlow: 0.62,
  surfaceGlow: 0.3,
  tint: '#ff5f7a',
  label: 'VERIFICATION RED',
  detail: 'failed',
  changedAt: 2000,
};

describe('vertebraConductorRoots', () => {
  it('does not add vertebra conductor roots to the brainstem input', () => {
    const conductor = deriveVertebraConductorRoots({
      kind: 'input',
      focused: true,
      originLocal: [0, -1.08, -0.42],
      targetLocal: [0.28, -0.78, 0.16],
      surfaceWidth: 0.98,
      surfaceHeight: 0.28,
    });

    expect(conductor.roots).toHaveLength(0);
    expect(conductor.rootNode).toBeNull();
    expect(conductor.nodeOpacity).toBe(0);
  });

  it('fans paired upper and lower roots from the vertebra to the spine-side edge of a focused surface', () => {
    const conductor = deriveVertebraConductorRoots({
      kind: 'content',
      focused: true,
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      surfaceWidth: 1.08,
      surfaceHeight: 0.9,
    });

    expect(conductor.roots).toHaveLength(4);
    expect(conductor.roots.filter((root) => root.pair === 'upper')).toHaveLength(2);
    expect(conductor.roots.filter((root) => root.pair === 'lower')).toHaveLength(2);
    expect(conductor.roots[0].end[1]).toBeGreaterThan(-1.03);
    expect(conductor.roots[3].end[1]).toBeLessThan(-1.03);
    expect(conductor.roots[0].end[0]).toBeGreaterThan(0.04);
    expect(conductor.roots[0].end[0]).toBeLessThan(0.86);
    expect(conductor.roots[0].opacity).toBeLessThan(0.1);
    expect(conductor.roots[0].radius).toBeLessThan(0.0025);
    expect(conductor.nodeOpacity).toBeLessThan(0.15);
    expect(conductor.gripNodes).toHaveLength(4);
  });

  it('dims and thins waiting roots without moving the anatomical grip to the far face', () => {
    const focused = deriveVertebraConductorRoots({
      kind: 'approval',
      focused: true,
      originLocal: [0.04, -1.3, -0.35],
      targetLocal: [0.8, -1.12, 0.28],
      surfaceWidth: 1.02,
      surfaceHeight: 0.78,
    });
    const waiting = deriveVertebraConductorRoots({
      kind: 'approval',
      focused: false,
      waitingIndex: 1,
      originLocal: [0.04, -1.3, -0.35],
      targetLocal: [0.8, -1.12, 0.28],
      surfaceWidth: 1.02,
      surfaceHeight: 0.78,
    });

    expect(waiting.roots[0].opacity).toBeLessThan(focused.roots[0].opacity);
    expect(waiting.roots[0].radius).toBeLessThan(focused.roots[0].radius);
    expect(waiting.roots[0].end[0]).toBeLessThan(0.8);
    expect(waiting.nodeOpacity).toBeLessThan(focused.nodeOpacity);
  });

  it('thickens and brightens focused roots during live work metabolism', () => {
    const resting = deriveVertebraConductorRoots({
      kind: 'content',
      focused: true,
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      surfaceWidth: 1.08,
      surfaceHeight: 0.9,
    });
    const working = deriveVertebraConductorRoots({
      kind: 'content',
      focused: true,
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      surfaceWidth: 1.08,
      surfaceHeight: 0.9,
      metabolism: workingMetabolism,
    });

    expect(working.roots[0].opacity).toBeGreaterThan(resting.roots[0].opacity);
    expect(working.roots[0].radius).toBeGreaterThan(resting.roots[0].radius);
    expect(working.nodeOpacity).toBeGreaterThan(resting.nodeOpacity);
  });

  it('keeps outcome scars anchored to the focused vertebra roots', () => {
    const resting = deriveVertebraConductorRoots({
      kind: 'content',
      focused: true,
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      surfaceWidth: 1.08,
      surfaceHeight: 0.9,
    });
    const scarred = deriveVertebraConductorRoots({
      kind: 'content',
      focused: true,
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      surfaceWidth: 1.08,
      surfaceHeight: 0.9,
      outcome: scarImprint,
    });
    const waitingScarred = deriveVertebraConductorRoots({
      kind: 'content',
      focused: false,
      waitingIndex: 0,
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      surfaceWidth: 1.08,
      surfaceHeight: 0.9,
      outcome: scarImprint,
    });

    expect(scarred.roots[0].opacity).toBeGreaterThan(resting.roots[0].opacity);
    expect(scarred.roots[0].radius).toBeGreaterThan(resting.roots[0].radius);
    expect(waitingScarred.roots[0].opacity).toBeLessThan(scarred.roots[0].opacity);
  });
});
