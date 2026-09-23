import { describe, expect, it } from 'vitest';
import { deriveBeingPresentation, type BeingFacts } from './semanticKernel';

const base = (overrides: Partial<BeingFacts> = {}): BeingFacts => ({
  lifecycle: 'rest',
  transport: 'connected',
  projection: 'fresh',
  mirrorStatus: 'online',
  hasSnapshot: true,
  taskActivity: 'idle',
  verification: 'unknown',
  stop: 'clear',
  ...overrides,
});

describe('deriveBeingPresentation', () => {
  it('keeps authority fields out of the presentation contract', () => {
    type AuthorityField = 'canExecute' | 'approved' | 'authorized' | 'allowed';
    type NoAuthorityFields = Extract<keyof BeingFacts, AuthorityField> extends never ? true : false;
    const typeContract: NoAuthorityFields = true;
    const presentation = deriveBeingPresentation(base({ approvalPending: true }));

    expect(typeContract).toBe(true);
    expect(Object.keys(presentation)).not.toEqual(expect.arrayContaining([
      'canExecute', 'approved', 'authorized', 'allowed',
    ]));
  });

  it('keeps an untouched being calm and resting', () => {
    expect(deriveBeingPresentation(base())).toEqual({
      phase: 'resting',
      taskState: 'idle',
      coherence: 'fresh',
      motion: 'calm',
      attention: 'none',
      signals: [],
      workers: [],
    });
  });

  it('separates arrival and human attention from active work', () => {
    expect(deriveBeingPresentation(base({ lifecycle: 'arriving' }))).toMatchObject({ phase: 'arriving', motion: 'materialize' });
    expect(deriveBeingPresentation(base({ inputActive: true, hasInput: true }))).toMatchObject({ phase: 'listening', attention: 'human' });
    expect(deriveBeingPresentation(base({ hasUnderstanding: true }))).toMatchObject({ phase: 'understanding', taskState: 'understood' });
  });

  it('maps planning, approval hold, acting, and verification to distinct postures', () => {
    expect(deriveBeingPresentation(base({ hasPlan: true }))).toMatchObject({ phase: 'planning', motion: 'attention', taskState: 'preparing' });
    expect(deriveBeingPresentation(base({ approvalPending: true, hasPlan: true }))).toMatchObject({ phase: 'awaiting-human', motion: 'attention', taskState: 'needs-permission' });
    expect(deriveBeingPresentation(base({ taskActivity: 'streaming', workers: ['active'] }))).toMatchObject({ phase: 'acting', motion: 'conduct', taskState: 'working' });
    expect(deriveBeingPresentation(base({ taskActivity: 'checking', verification: 'pending' }))).toMatchObject({ phase: 'verifying', motion: 'verify', taskState: 'checking' });
  });

  it('never collapses completion and verification', () => {
    expect(deriveBeingPresentation(base({ taskActivity: 'complete', verification: 'pass' }))).toMatchObject({ phase: 'resting', taskState: 'done-verified', coherence: 'fresh' });
    expect(deriveBeingPresentation(base({ taskActivity: 'complete', verification: 'unknown' }))).toMatchObject({ phase: 'resting', taskState: 'done-unverified', coherence: 'unverified' });
    expect(deriveBeingPresentation(base({ taskActivity: 'complete', verification: 'fail' }))).toMatchObject({ phase: 'recovering', taskState: 'done-unverified', coherence: 'degraded', motion: 'reabsorb' });
  });

  it('keeps stale and degraded distinct from failure', () => {
    expect(deriveBeingPresentation(base({ projection: 'stale', mirrorStatus: 'stale' }))).toMatchObject({ phase: 'stale', taskState: 'stale', coherence: 'stale' });
    expect(deriveBeingPresentation(base({ transport: 'disconnected', projection: 'unavailable', hasSnapshot: false }))).toMatchObject({ phase: 'degraded', coherence: 'degraded' });
    expect(deriveBeingPresentation(base({ taskActivity: 'failed', verification: 'fail' }))).toMatchObject({ phase: 'recovering', taskState: 'failed', coherence: 'degraded', motion: 'reabsorb' });
  });

  it('keeps a real approval boundary visible while preserving stale or degraded coherence', () => {
    expect(deriveBeingPresentation(base({ approvalPending: true, projection: 'stale', mirrorStatus: 'stale' }))).toMatchObject({
      phase: 'awaiting-human',
      taskState: 'needs-permission',
      coherence: 'stale',
      motion: 'attention',
    });
    expect(deriveBeingPresentation(base({
      approvalPending: true,
      transport: 'disconnected',
      projection: 'unavailable',
      hasSnapshot: false,
    }))).toMatchObject({
      phase: 'awaiting-human',
      taskState: 'needs-permission',
      coherence: 'degraded',
      motion: 'attention',
    });
  });

  it('does not present a disconnected empty projection as active startup', () => {
    expect(deriveBeingPresentation(base({
      lifecycle: 'booting',
      transport: 'disconnected',
      projection: 'unknown',
      hasSnapshot: false,
    }))).toMatchObject({
      phase: 'degraded',
      coherence: 'degraded',
    });
  });

  it('makes emergency stop dominant and freezes the action posture', () => {
    expect(deriveBeingPresentation(base({ stop: 'engaged', taskActivity: 'streaming', workers: ['active'] }))).toEqual({
      phase: 'stopped',
      taskState: 'stopped',
      coherence: 'stopped',
      motion: 'stop',
      attention: 'none',
      signals: ['emergency-stop', 'worker-active'],
      workers: ['active'],
    });
  });

  it('derives bounded worker lifecycle signals without exposing identities', () => {
    expect(deriveBeingPresentation(base({ workers: ['requested', 'admitted', 'active', 'returned', 'dissolved'] })).signals).toEqual([
      'worker-requested', 'worker-born', 'worker-active', 'worker-returned', 'worker-dissolved',
    ]);
  });

  it('keeps a worker held at the capability boundary rather than calling it returned', () => {
    const presentation = deriveBeingPresentation(base({ workers: ['awaiting-capability'] }));
    expect(presentation).toMatchObject({ phase: 'acting', taskState: 'working' });
    expect(presentation.signals).toEqual(['worker-active']);
  });

  it('distinguishes reflex reuse from model-like planning and preserves memory evidence', () => {
    const presentation = deriveBeingPresentation(base({ reflexUsed: true, memoryRecalled: true, route: 'local', taskActivity: 'streaming' }));
    expect(presentation).toMatchObject({ phase: 'reflex', motion: 'conduct', taskState: 'working' });
    expect(presentation.signals).toEqual(['memory-recalled', 'reflex-reused', 'route-local']);
  });

  it('surfaces refusal, rollback, route, dissent, and learning as signals only', () => {
    const presentation = deriveBeingPresentation(base({
      taskActivity: 'refused',
      rollback: true,
      route: 'cloud',
      councilDissent: true,
      curriculumMastered: true,
      injectionBlocked: true,
    }));
    expect(presentation.phase).toBe('recovering');
    expect(presentation.motion).toBe('reabsorb');
    expect(presentation.signals).toEqual([
      'rollback', 'injection-blocked', 'refusal', 'route-cloud', 'council-dissent', 'curriculum-mastered',
    ]);
  });

  it('uses semantic materialization and reabsorption motions only for measured lifecycle states', () => {
    expect(deriveBeingPresentation(base({ lifecycle: 'materializing' }))).toMatchObject({ motion: 'materialize' });
    expect(deriveBeingPresentation(base({ lifecycle: 'reabsorbing', rollback: true }))).toMatchObject({ motion: 'reabsorb' });
    expect(deriveBeingPresentation(base({ taskActivity: 'refused' }))).toMatchObject({ motion: 'refuse' });
  });
});
