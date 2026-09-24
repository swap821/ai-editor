import { describe, expect, it } from 'vitest';
import { deriveBeingPresentation } from './beingPresentation';
import { deriveBeingScenePresentation } from './beingScenePresentation';

const input = (overrides: Partial<Parameters<typeof deriveBeingPresentation>[0]> = {}) => deriveBeingPresentation({
  mirrorSnapshot: {
    status: 'online',
    projection: 'fresh',
    snapshotRequired: false,
    snapshotReceivedAt: '2026-09-22T00:00:00.000Z',
    activeWorkers: [],
  },
  connectionState: 'connected',
  activeTurn: 'idle',
  pendingApproval: false,
  emergencyStop: false,
  recentSemanticSignals: [],
  reducedMotion: false,
  qualityTier: 'high',
  ...overrides,
});

describe('being scene presentation', () => {
  it('keeps the settled being quiet and low-contrast', () => {
    expect(deriveBeingScenePresentation(input())).toMatchObject({
      posture: 'rest',
      motionIntensity: 1,
      energy: 0.12,
      haloOpacity: expect.any(Number),
    });
  });

  it('maps supervised work to the hold posture without inventing approval', () => {
    const scene = deriveBeingScenePresentation(input({ pendingApproval: true }));

    expect(scene).toMatchObject({ posture: 'hold', isHeld: true });
    expect(scene.haloOpacity).toBeGreaterThan(0);
  });

  it('makes stale and stopped states calm, visible, and motion-safe', () => {
    const stale = deriveBeingScenePresentation(input({
      mirrorSnapshot: {
        status: 'stale',
        projection: 'stale',
        snapshotRequired: true,
        snapshotReceivedAt: '2026-09-22T00:00:00.000Z',
        activeWorkers: ['worker-1'],
      },
    }));
    const stopped = deriveBeingScenePresentation(input({ emergencyStop: true }));

    expect(stale).toMatchObject({ posture: 'error', motionIntensity: 1, isHeld: false });
    expect(stopped).toMatchObject({ posture: 'error', motionIntensity: 0, energy: 0 });
    expect(stopped.haloOpacity).toBeGreaterThan(0);
  });

  it('honours reduced motion while retaining semantic intensity', () => {
    const scene = deriveBeingScenePresentation(input({
      activeTurn: 'acting',
      reducedMotion: true,
      mirrorSnapshot: {
        status: 'online',
        projection: 'fresh',
        snapshotRequired: false,
        snapshotReceivedAt: '2026-09-22T00:00:00.000Z',
        activeWorkers: ['worker-1'],
      },
    }));

    expect(scene.posture).toBe('stream');
    expect(scene.energy).toBeGreaterThan(0);
    expect(scene.motionIntensity).toBe(0);
    expect(scene.flow).toBeGreaterThan(0);
  });
});
