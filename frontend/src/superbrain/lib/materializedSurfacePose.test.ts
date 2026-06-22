import { describe, expect, it } from 'vitest';
import { deriveMaterializedSurfacePose } from './materializedSurfacePose';

describe('materializedSurfacePose', () => {
  it('leaves the input surface attached to the brainstem placement', () => {
    const pose = deriveMaterializedSurfacePose({
      kind: 'input',
      focused: false,
      targetLocal: [0.28, -0.78, 0.16],
    });
    expect(pose.targetLocal).toEqual([0.28, -0.78, 0.16]);
    expect(pose.scale).toBe(1);
    expect(pose.opacity).toBe(1);
  });

  it('pulls the focused workspace surface to the centered forward working field', () => {
    const pose = deriveMaterializedSurfacePose({
      kind: 'approval',
      focused: true,
      targetLocal: [0.76, -1.17, 0.2],
    });
    expect(pose.targetLocal[0]).toBe(0);
    expect(pose.targetLocal[1]).toBeGreaterThan(-1.17);
    expect(pose.targetLocal[1]).toBeLessThan(-0.9);
    expect(pose.targetLocal[2]).toBeGreaterThan(0.2);
    expect(pose.scale).toBeGreaterThan(1);
  });

  it('parks waiting surfaces in the open field and dims them in stable order', () => {
    const first = deriveMaterializedSurfacePose({
      kind: 'content',
      focused: false,
      targetLocal: [0.82, -1.1, 0.24],
      waitingIndex: 0,
    });
    const second = deriveMaterializedSurfacePose({
      kind: 'content',
      focused: false,
      targetLocal: [0.82, -1.1, 0.24],
      waitingIndex: 1,
    });

    expect(first.targetLocal[0]).toBeGreaterThan(0);
    expect(second.targetLocal[0]).toBeGreaterThan(0);
    expect(first.targetLocal[2]).toBeLessThan(0.24);
    expect(second.targetLocal[1]).toBeLessThan(first.targetLocal[1]);
    expect(second.scale).toBeLessThan(first.scale);
    expect(second.opacity).toBeLessThan(first.opacity);
  });
});
