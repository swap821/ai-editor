import { describe, expect, it } from 'vitest';
import {
  advanceCortexAttentionPulse,
  advanceCortexAttentionSpring,
  CORTEX_COMPOSER_INTAKE_LOCAL,
  createCortexAttentionPulseState,
  createCortexAttentionSpring,
  deriveCortexAttentionPaths,
  retargetCortexAttentionPulse,
  retargetCortexAttentionSpring,
} from './cortexAttentionPaths';

describe('deriveCortexAttentionPaths', () => {
  it('preserves the quiet, untargeted cortical currents when no workspace owns attention', () => {
    const paths = deriveCortexAttentionPaths({
      origin: [0, 0, 0],
      target: null,
      activity: 0.5,
      convergence: 0.25,
      count: 3,
    });

    expect(paths[0][0]).toEqual([0.08, 0.0304, 0.0192]);
    expect(paths[0][1][0]).toBeCloseTo(0.28);
    expect(paths[0][1][1]).toBeCloseTo(0.1064);
    expect(paths[0][1][2]).toBeCloseTo(0.0672);
    expect(paths[0][2][0]).toBeCloseTo(0.1638);
    expect(paths[0][2][1]).toBeCloseTo(0.062244);
    expect(paths[0][2][2]).toBeCloseTo(0.039312);
  });

  it('turns every active path toward the focused workspace seat and tightens its fan as attention converges', () => {
    const input = {
      origin: [0, 0.1, 0] as const,
      target: [0.4, -1.2, 0.2] as const,
      activity: 0.7,
      count: 3,
    };
    const open = deriveCortexAttentionPaths({ ...input, convergence: 0.2 });
    const focused = deriveCortexAttentionPaths({ ...input, convergence: 0.9 });
    const targetVector = input.target.map((value, index) => value - input.origin[index]);
    const dotWithTarget = (point: readonly number[]) => point.reduce(
      (sum, value, index) => sum + (value - input.origin[index]) * targetVector[index],
      0,
    );

    expect(open).toHaveLength(3);
    expect(open.every((path) => dotWithTarget(path[1]) > 0)).toBe(true);
    expect(focused.every((path) => dotWithTarget(path[1]) > 0)).toBe(true);
    const endpointDistance = (path: readonly (readonly number[])[]) => Math.hypot(
      path[2][0] - input.origin[0],
      path[2][1] - input.origin[1],
      path[2][2] - input.origin[2],
    );
    expect(endpointDistance(focused[1])).toBeLessThan(endpointDistance(open[1]));
    expect(open.every((path) => path.flat().every(Number.isFinite))).toBe(true);
  });

  it('extends a targeted current far enough to read as attention beyond the cortex', () => {
    const origin = [0, 0.1, 0] as const;
    const paths = deriveCortexAttentionPaths({
      origin,
      target: [0, -1.08, -0.42],
      activity: 0.2,
      convergence: 0.9,
      count: 3,
    });
    const centerEndpoint = paths[1][2];
    const endpointDistance = Math.hypot(...centerEndpoint.map((value, index) => value - origin[index]));

    expect(endpointDistance).toBeGreaterThan(0.45);
    expect(endpointDistance).toBeLessThan(0.8);
  });

  it('lands the single input-attention current on the intake instead of stopping inside the body', () => {
    const intake = CORTEX_COMPOSER_INTAKE_LOCAL;
    const paths = deriveCortexAttentionPaths({
      origin: [0, 0.1, 0],
      target: intake,
      activity: 0.2,
      convergence: 0.9,
      count: 1,
      contactTarget: true,
    });

    expect(paths).toHaveLength(1);
    expect(paths[0][2][0]).toBeCloseTo(intake[0], 8);
    expect(paths[0][2][1]).toBeCloseTo(intake[1], 8);
    expect(paths[0][2][2]).toBeCloseTo(intake[2], 8);
  });

  it('falls back safely for a zero-length aim and handles a vertical aim', () => {
    const zeroAim = deriveCortexAttentionPaths({
      origin: [0, 0, 0],
      target: [0, 0, 0],
      activity: 0.5,
      convergence: 0.5,
      count: 1,
    });
    const verticalAim = deriveCortexAttentionPaths({
      origin: [0, 0, 0],
      target: [0, -1, 0],
      activity: 0.5,
      convergence: 0.5,
      count: 3,
    });

    expect(zeroAim[0][1][0]).toBeCloseTo(0.28);
    expect(zeroAim[0][1][1]).toBeCloseTo(0.1064);
    expect(zeroAim[0][1][2]).toBeCloseTo(0.0672);
    expect(verticalAim[0].flat().every(Number.isFinite)).toBe(true);
    expect(verticalAim.every((path) => path[1][1] < 0)).toBe(true);
  });

  it('retargets from the in-flight position and velocity instead of snapping or queuing', () => {
    const start = deriveCortexAttentionPaths({
      origin: [0, 0, 0], target: null, activity: 0.5, convergence: 0.4, count: 1,
    });
    const spring = createCortexAttentionSpring(start);
    const firstTarget = deriveCortexAttentionPaths({
      origin: [0, 0, 0], target: [0, 1, 0], activity: 0.5, convergence: 0.4, count: 1,
    });
    const secondTarget = deriveCortexAttentionPaths({
      origin: [0, 0, 0], target: [-1, 0, 0], activity: 0.5, convergence: 0.4, count: 1,
    });

    retargetCortexAttentionSpring(spring, firstTarget);
    expect(advanceCortexAttentionSpring(spring, 0.05)).toBe(true);
    const inFlightPosition = spring.positions[3];
    const inFlightVelocity = spring.velocities[3];
    expect(inFlightVelocity).toBeLessThan(0);

    retargetCortexAttentionSpring(spring, secondTarget);
    expect(spring.positions[3]).toBe(inFlightPosition);
    expect(spring.velocities[3]).toBe(inFlightVelocity);
    advanceCortexAttentionSpring(spring, 0.001);
    expect(spring.positions[3]).toBeLessThan(inFlightPosition);

    for (let frame = 0; frame < 30; frame += 1) advanceCortexAttentionSpring(spring, 1 / 60);
    expect(spring.positions[3]).toBe(spring.targets[3]);
    expect(spring.velocities[3]).toBe(0);
  });

  it('jumps to the semantic target and clears spring velocity for reduced motion', () => {
    const paths = deriveCortexAttentionPaths({
      origin: [0, 0, 0], target: null, activity: 0.5, convergence: 0.4, count: 1,
    });
    const spring = createCortexAttentionSpring(paths);
    const target = deriveCortexAttentionPaths({
      origin: [0, 0, 0], target: [0.6, -1, 0.2], activity: 0.5, convergence: 0.4, count: 1,
    });

    retargetCortexAttentionSpring(spring, target, true);

    expect([...spring.positions]).toEqual([...spring.targets]);
    expect([...spring.velocities]).toEqual(new Array(spring.positions.length).fill(0));
    expect(advanceCortexAttentionSpring(spring, 1 / 60)).toBe(false);
  });
});

describe('cortex attention pulse', () => {
  it('travels once on the empty-to-present edge and does not restart for continued typing', () => {
    const pulse = createCortexAttentionPulseState();

    expect(advanceCortexAttentionPulse(pulse, 1 / 60)).toBeNull();
    retargetCortexAttentionPulse(pulse, true);
    const firstFrame = advanceCortexAttentionPulse(pulse, 0.2);
    retargetCortexAttentionPulse(pulse, true);
    const nextFrame = advanceCortexAttentionPulse(pulse, 0.1);

    expect(firstFrame).toBeGreaterThan(0);
    expect(nextFrame).toBeGreaterThan(firstFrame!);
    expect(nextFrame).toBeLessThan(1);
  });

  it('returns the pulse to the cortex after clear, then starts a new transit only on a later draft edge', () => {
    const pulse = createCortexAttentionPulseState();
    retargetCortexAttentionPulse(pulse, true);

    let progress: number | null = 0;
    for (let frame = 0; frame < 90 && progress !== 1; frame += 1) {
      progress = advanceCortexAttentionPulse(pulse, 1 / 60);
    }
    expect(progress).toBe(1);

    retargetCortexAttentionPulse(pulse, false);
    const returnFrame = advanceCortexAttentionPulse(pulse, 0.18);
    expect(returnFrame).toBeCloseTo(0.75, 8);
    for (let frame = 0; frame < 90 && progress !== null; frame += 1) {
      progress = advanceCortexAttentionPulse(pulse, 1 / 60);
    }
    expect(progress).toBeNull();

    retargetCortexAttentionPulse(pulse, true);
    expect(advanceCortexAttentionPulse(pulse, 1 / 60)).toBeGreaterThan(0);
  });

  it('reverses the existing transit in place when the draft returns during reabsorption', () => {
    const pulse = createCortexAttentionPulseState();
    retargetCortexAttentionPulse(pulse, true);
    const inbound = advanceCortexAttentionPulse(pulse, 0.18);
    retargetCortexAttentionPulse(pulse, false);
    const outbound = advanceCortexAttentionPulse(pulse, 0.06);

    expect(inbound).toBeCloseTo(0.25, 8);
    expect(outbound).toBeCloseTo(1 / 6, 8);

    retargetCortexAttentionPulse(pulse, true);
    const resumed = advanceCortexAttentionPulse(pulse, 0.06);
    expect(resumed).toBeCloseTo(0.25, 8);
  });

  it('snaps to the intake and never travels when reduced motion is active', () => {
    const pulse = createCortexAttentionPulseState();
    retargetCortexAttentionPulse(pulse, true, true);

    expect(advanceCortexAttentionPulse(pulse, 1 / 60, true)).toBe(1);
    expect(pulse.elapsedSeconds).toBeGreaterThan(0);

    retargetCortexAttentionPulse(pulse, false, true);
    expect(advanceCortexAttentionPulse(pulse, 1 / 60, true)).toBeNull();
  });
});
