import { describe, expect, it } from 'vitest';
import { deriveBeingPresentation, type BeingPresentationInput } from './beingPresentation';

const input = (overrides: Partial<BeingPresentationInput> = {}): BeingPresentationInput => ({
  mirrorSnapshot: { status: 'online', projection: 'fresh', snapshotRequired: false, snapshotReceivedAt: '2026-01-01T00:00:00Z', activeWorkers: [] },
  connectionState: 'connected', activeTurn: 'idle', pendingApproval: false, emergencyStop: false,
  recentSemanticSignals: [], reducedMotion: false, qualityTier: 'high', ...overrides,
});

describe('being presentation derivation', () => {
  it('derives a quiet ready state only from a fresh connected mirror', () => {
    expect(deriveBeingPresentation(input())).toMatchObject({ phase: 'ready', continuityState: 'fresh', coherence: 1 });
  });

  it('lets stale continuity override activity so the UI cannot imply current work', () => {
    expect(deriveBeingPresentation(input({ activeTurn: 'acting', mirrorSnapshot: { ...input().mirrorSnapshot, status: 'stale', projection: 'stale' } }))).toMatchObject({ phase: 'stale', continuityState: 'stale' });
  });

  it('keeps approval and reflex semantically distinct from ordinary work', () => {
    expect(deriveBeingPresentation(input({ pendingApproval: true, activeTurn: 'acting' })).phase).toBe('awaiting-human');
    expect(deriveBeingPresentation(input({ activeTurn: 'reflex', recentSemanticSignals: ['reflex-reused'] })).phase).toBe('reflex');
  });

  it('does not let an older transient signal hold the organism in a stale visual phase', () => {
    expect(deriveBeingPresentation(input({ recentSemanticSignals: ['reflex-reused', 'worker-returned'] })).phase).toBe('ready');
  });

  it('makes emergency stop dominant and motionless', () => {
    expect(deriveBeingPresentation(input({ emergencyStop: true, activeTurn: 'acting', pendingApproval: true }))).toMatchObject({ phase: 'stopped', energy: 0, motionIntensity: 0, continuityState: 'stopped' });
  });

  it('dampens motion for accessibility and quality without changing authority', () => {
    const reduced = deriveBeingPresentation(input({ reducedMotion: true, qualityTier: 'low', activeTurn: 'acting' }));
    expect(reduced.motionIntensity).toBe(0);
    expect(reduced.phase).toBe('acting');
    expect(reduced.workerCount).toBe(0);
  });
});
