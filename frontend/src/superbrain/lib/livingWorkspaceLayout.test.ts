import { describe, expect, it } from 'vitest';
import { deriveBrainPresenceLayout, deriveLivingWorkspacePose } from './livingWorkspaceLayout';

describe('livingWorkspaceLayout', () => {
  it('leaves the brainstem input at its authored anchor', () => {
    const pose = deriveLivingWorkspacePose({
      kind: 'input',
      focused: false,
      targetLocal: [0.28, -0.78, 0.16],
    });
    expect(pose.targetLocal).toEqual([0.28, -0.78, 0.16]);
    expect(pose.scale).toBe(1);
    expect(pose.opacity).toBe(1);
  });

  it('pulls the focused workspace to the centered forward working field', () => {
    const pose = deriveLivingWorkspacePose({
      kind: 'content',
      focused: true,
      targetLocal: [0.82, -1.1, 0.24],
    });
    expect(pose.targetLocal[0]).toBe(0);
    expect(pose.targetLocal[1]).toBeLessThan(-0.9);
    expect(pose.targetLocal[2]).toBeGreaterThan(0.24);
    expect(pose.scale).toBeGreaterThan(1);
    expect(pose.opacity).toBe(1);
  });

  it('parks waiting workspaces in the open field before wrapping around the body', () => {
    const first = deriveLivingWorkspacePose({
      kind: 'content',
      focused: false,
      targetLocal: [0.82, -1.1, 0.24],
      waitingIndex: 0,
    });
    const second = deriveLivingWorkspacePose({
      kind: 'approval',
      focused: false,
      targetLocal: [0.76, -1.17, 0.2],
      waitingIndex: 1,
    });
    const third = deriveLivingWorkspacePose({
      kind: 'content',
      focused: false,
      targetLocal: [0.82, -1.1, 0.24],
      waitingIndex: 2,
    });

    expect(first.targetLocal[0]).toBeGreaterThan(0);
    expect(second.targetLocal[0]).toBeGreaterThan(0);
    expect(third.targetLocal[0]).toBeLessThan(0);
    expect(second.targetLocal[1]).toBeLessThan(first.targetLocal[1]);
    expect(third.targetLocal[1]).toBeLessThan(second.targetLocal[1]);
    expect(second.scale).toBeLessThan(first.scale);
    expect(third.opacity).toBeLessThan(second.opacity);
  });

  it('lets the resting companion brain follow the pointer before work exists', () => {
    const empty = deriveBrainPresenceLayout({ workspaceCount: 0, viewportWidth: 1440, viewportHeight: 900 });

    expect(empty.mode).toBe('rest');
    expect(empty.mainBrainScale).toBe(1);
    expect(empty.miniBrainScale).toBe(0.205);
    expect(empty.pointerInfluence).toBe(1);
    expect(empty.miniBrainPosition[0]).toBeGreaterThan(0);
  });

  it('docks the mini-brain over the conductor when workspaces exist', () => {
    const rest = deriveBrainPresenceLayout({ workspaceCount: 0, viewportWidth: 1440, viewportHeight: 900 });
    const docked = deriveBrainPresenceLayout({ workspaceCount: 2, viewportWidth: 1440, viewportHeight: 900 });

    expect(docked.mode).toBe('docked');
    expect(docked.miniBrainPosition[0]).toBe(0);
    expect(docked.miniBrainPosition[1]).toBeGreaterThan(rest.miniBrainPosition[1]);
    expect(docked.pointerInfluence).toBeLessThan(0.14);
    expect(docked.miniBrainOpacity).toBeGreaterThan(rest.miniBrainOpacity);
    expect(docked.mainBrainScale).toBeLessThanOrEqual(1);
  });

  it('compresses the conductor pair under high workspace load and compact viewports', () => {
    const desktop = deriveBrainPresenceLayout({ workspaceCount: 2, viewportWidth: 1440, viewportHeight: 900 });
    const packed = deriveBrainPresenceLayout({ workspaceCount: 7, viewportWidth: 390, viewportHeight: 700 });

    expect(packed.mode).toBe('docked');
    expect(packed.compactness).toBeGreaterThan(desktop.compactness);
    expect(packed.mainBrainScale).toBeLessThan(desktop.mainBrainScale);
    expect(packed.mainBrainScale).toBeGreaterThanOrEqual(0.76);
    expect(packed.miniBrainScale).toBeLessThan(desktop.miniBrainScale);
    expect(packed.pointerInfluence).toBeLessThan(desktop.pointerInfluence);
    expect(packed.miniBrainPosition[1]).toBeGreaterThan(desktop.miniBrainPosition[1]);
  });

  it('pulls materialized work inward on compact portrait viewports', () => {
    const desktop = deriveLivingWorkspacePose({
      kind: 'content',
      focused: true,
      targetLocal: [0.82, -1.1, 0.24],
      viewportWidth: 1440,
      viewportHeight: 900,
    });
    const mobile = deriveLivingWorkspacePose({
      kind: 'content',
      focused: true,
      targetLocal: [0.82, -1.1, 0.24],
      viewportWidth: 390,
      viewportHeight: 844,
    });
    const waiting = deriveLivingWorkspacePose({
      kind: 'content',
      focused: false,
      targetLocal: [0.82, -1.1, 0.24],
      waitingIndex: 1,
      viewportWidth: 390,
      viewportHeight: 844,
    });

    expect(mobile.scale).toBeLessThan(desktop.scale);
    expect(mobile.targetLocal[0]).toBeGreaterThan(desktop.targetLocal[0]);
    expect(mobile.targetLocal[1]).toBeGreaterThan(desktop.targetLocal[1]);
    expect(waiting.scale).toBeLessThan(0.54);
    expect(waiting.targetLocal[1]).toBeGreaterThan(-1.62);
  });
});
