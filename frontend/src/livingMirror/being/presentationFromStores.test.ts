import { beforeEach, describe, expect, it } from 'vitest';
import { __resetConversationPhaseForTests, setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import type { CortexMirrorState } from '../../superbrain/lib/mirrorStore';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';
import { beingFactsFromStores, beingPresentationFromStores, beingStatusText } from './presentationFromStores';

const tabs = { tabs: [], focusId: null, attention: null } as TabSnapshot;

function mirror(overrides: Partial<CortexMirrorState> = {}): CortexMirrorState {
  return {
    status: 'online',
    connection: 'connected',
    projection: 'fresh',
    compatibility: null,
    snapshotReceivedAt: '2026-09-22T00:00:00.000Z',
    observations: {} as CortexMirrorState['observations'],
    metrics: {},
    pendingEvents: 0,
    phase: 'idle',
    activeCastes: [],
    activeMissions: [],
    activeWorkers: [],
    activeModels: [],
    missions: {},
    workers: {},
    approvals: {},
    verifications: {},
    approvalRequired: false,
    lastVerification: null,
    lastAnnouncement: null,
    snapshotRequired: false,
    recentEvents: [],
    lastEventId: null,
    lastTurnStartedEventId: null,
    lastVerificationEventId: null,
    turnAttributionInvalidated: false,
    bootFacts: null,
    ...overrides,
  } as CortexMirrorState;
}

describe('presentation facts from admitted stores', () => {
  beforeEach(() => {
    __resetConversationPhaseForTests();
    setConversationPhase('idle');
  });

  it('maps backend worker lifecycle names into bounded presentation states', () => {
    const facts = beingFactsFromStores(mirror({
      workers: {
        requested: { id: 'requested', state: 'requested' } as never,
        admitted: { id: 'admitted', state: 'admitted' } as never,
        started: { id: 'started', state: 'started' } as never,
        waiting: { id: 'waiting', state: 'awaiting_capability' } as never,
        done: { id: 'done', state: 'completed' } as never,
        dissolved: { id: 'dissolved', state: 'dissolved' } as never,
      },
    }), tabs);
    expect(facts.workers).toEqual(expect.arrayContaining([
      expect.objectContaining({ workerId: 'requested', state: 'requested' }),
      expect.objectContaining({ workerId: 'admitted', state: 'admitted' }),
      expect.objectContaining({ workerId: 'started', state: 'active' }),
      expect.objectContaining({ workerId: 'waiting', state: 'awaiting-capability' }),
      expect.objectContaining({ workerId: 'done', state: 'returned' }),
      expect.objectContaining({ workerId: 'dissolved', state: 'dissolved' }),
    ]));
  });

  it('preserves worker identity and deterministic cursor ordering in semantic facts', () => {
    const facts = beingFactsFromStores(mirror({
      workers: {
        'worker-z': { id: 'worker-z', state: 'started', cursor: 8 } as never,
        'worker-a': { id: 'worker-a', state: 'awaiting_capability', cursor: 3 } as never,
      },
    }), tabs);

    expect(facts.workers).toEqual([
      { workerId: 'worker-z', state: 'active', cursor: 8 },
      { workerId: 'worker-a', state: 'awaiting-capability', cursor: 3 },
    ]);
  });

  it('reconstructs active worker identities from a measured snapshot after a cold load', () => {
    const facts = beingFactsFromStores(mirror({
      projection: 'snapshot',
      activeWorkers: ['worker-z', 'worker-a'],
      observations: {
        activeWorkers: {
          status: 'measured',
          source: 'mirror/snapshot',
          observedAt: null,
          receivedAt: '2026-09-26T00:00:00.000Z',
          cursor: 42,
        },
      } as CortexMirrorState['observations'],
    }), tabs);

    expect(facts.workers).toEqual([
      { workerId: 'worker-a', state: 'active', cursor: 42 },
      { workerId: 'worker-z', state: 'active', cursor: 42 },
    ]);
  });

  it('lets the measured snapshot roster replace pre-snapshot worker history', () => {
    const facts = beingFactsFromStores(mirror({
      projection: 'snapshot',
      activeWorkers: ['worker-current'],
      observations: {
        activeWorkers: {
          status: 'measured',
          source: 'mirror/snapshot',
          observedAt: null,
          receivedAt: '2026-09-26T00:00:00.000Z',
          cursor: 10,
        },
      } as CortexMirrorState['observations'],
      workers: {
        'worker-current': { id: 'worker-current', state: 'completed', cursor: 7 } as never,
        'worker-old': { id: 'worker-old', state: 'started', cursor: 5 } as never,
      },
    }), tabs);

    expect(facts.workers).toEqual([
      { workerId: 'worker-current', state: 'active', cursor: 10 },
    ]);
  });

  it('caps worker posture to the eight most recent workers while retaining active work first', () => {
    const workers = Object.fromEntries(Array.from({ length: 12 }, (_, index) => [
      `worker-${index}`,
      {
        id: `worker-${index}`,
        missionId: null,
        state: index < 2 ? 'started' : 'completed',
        observedAt: null,
        cursor: index + 1,
        payload: {},
      },
    ])) as CortexMirrorState['workers'];
    const facts = beingFactsFromStores(mirror({ workers }), tabs);
    expect(facts.workers).toHaveLength(8);
    expect(facts.workers?.slice(0, 2).map((worker) => worker.state)).toEqual(['active', 'active']);
  });

  it('maps tab materialization and reabsorption lifecycle to presentation-only facts', () => {
    const content = { id: 'surface', kind: 'content', lifecycle: 'reaching', content: null, input: null, approval: null };
    expect(beingFactsFromStores(mirror(), { ...tabs, tabs: [content as never] }).lifecycle).toBe('materializing');
    expect(beingFactsFromStores(mirror(), { ...tabs, tabs: [{ ...content, lifecycle: 'retracting' } as never] }).lifecycle).toBe('reabsorbing');
  });

  it('does not infer route or authority from incomplete recent-event summaries', () => {
    const facts = beingFactsFromStores(mirror({
      approvalRequired: true,
      recentEvents: [{ id: 1, type: 'route.selected', summary: 'route selected', occurredAt: null, receivedAt: new Date().toISOString() }],
    }), tabs);
    expect(facts.route).toBe('unknown');
    expect(beingPresentationFromStores(mirror({ projection: 'stale', status: 'stale' }), tabs)).toMatchObject({
      phase: 'stale',
      coherence: 'stale',
    });
  });

  it('treats refusal and emergency stop as measured presentation states', () => {
    const refused = beingPresentationFromStores(mirror({
      recentEvents: [{ id: 2, type: 'security.refusal.recorded', summary: 'refused', occurredAt: null, receivedAt: new Date().toISOString() }],
    }), tabs);
    expect(refused).toMatchObject({ phase: 'recovering', taskState: 'refused' });

    const stopped = beingPresentationFromStores(mirror({
      recentEvents: [{ id: 3, type: 'governance.emergency_stop.engaged', summary: 'stop', occurredAt: null, receivedAt: new Date().toISOString() }],
    }), tabs);
    expect(stopped).toMatchObject({ phase: 'stopped', taskState: 'stopped', motion: 'stop' });
  });

  it('announces task outcomes without collapsing verified and unverified work', () => {
    const verified = beingPresentationFromStores(mirror(), {
      ...tabs,
      tabs: [{ id: 'verified', kind: 'content', lifecycle: 'open', content: { streaming: false, verifyVerdict: 'pass' } } as never],
      focusId: 'verified',
    });
    const unverified = beingPresentationFromStores(mirror(), {
      ...tabs,
      tabs: [{ id: 'unverified', kind: 'content', lifecycle: 'open', content: { streaming: false } } as never],
      focusId: 'unverified',
    });
    const refused = beingPresentationFromStores(mirror({
      recentEvents: [{ id: 4, type: 'security.refusal.recorded', summary: 'refused', occurredAt: null, receivedAt: new Date().toISOString() }],
    }), tabs);

    expect(beingStatusText(verified)).toBe('GAGOS finished the task and verification passed.');
    expect(beingStatusText(unverified)).toBe('GAGOS finished the work, but it is not verified yet.');
    expect(beingStatusText(refused)).toBe('GAGOS did not do that because it would have exceeded your permission.');
  });

  it('announces that a disconnected organism is only showing its resting view', () => {
    const disconnected = beingPresentationFromStores(mirror({
      status: 'offline',
      connection: 'disconnected',
      projection: 'unknown',
      snapshotReceivedAt: null,
    }), tabs);

    expect(disconnected.phase).toBe('degraded');
    expect(beingStatusText(disconnected)).toBe('GAGOS has no live state to show; the organism is in its resting view.');
  });

  it('does not let a retained verification promote a new content surface', () => {
    const unverified = beingPresentationFromStores(mirror({
      lastVerification: { verdict: 'pass', evidenceId: 'older-result' },
    }), {
      ...tabs,
      tabs: [{ id: 'new-work', kind: 'content', lifecycle: 'live', content: { streaming: false } } as never],
      focusId: 'new-work',
    });

    expect(unverified).toMatchObject({ taskState: 'done-unverified', coherence: 'unverified' });
  });

  it('does not carry a retained mirror verification into a new turn', () => {
    const mirrorState = mirror({
      lastVerification: { verdict: 'pass', evidenceId: 'older-result' },
      recentEvents: [
        { id: 1, type: 'verification.passed', summary: 'older pass', occurredAt: null, receivedAt: '2026-09-22T00:00:01.000Z' },
        { id: 2, type: 'turn.started', summary: 'new turn', occurredAt: null, receivedAt: '2026-09-22T00:00:02.000Z' },
      ],
    });

    const nextTurn = beingPresentationFromStores(mirrorState, tabs, 'complete');
    expect(nextTurn).toMatchObject({ taskState: 'done-unverified', coherence: 'unverified' });
  });

  it('does not treat a focused prior artifact verdict as current-turn evidence', () => {
    const priorVerifiedArtifact = {
      id: 'prior-verified-artifact',
      kind: 'content',
      lifecycle: 'live',
      content: { streaming: false, verifyVerdict: 'pass' },
    };
    const nextTurn = beingPresentationFromStores(mirror({
      recentEvents: [
        { id: 1, type: 'turn.started', summary: 'new turn', occurredAt: null, receivedAt: '2026-09-22T00:00:02.000Z' },
      ],
    }), {
      ...tabs,
      tabs: [priorVerifiedArtifact as never],
      focusId: priorVerifiedArtifact.id,
    }, 'complete');

    expect(nextTurn).toMatchObject({ taskState: 'done-unverified', coherence: 'unverified' });
    expect(nextTurn.signals).not.toContain('verification-pass');
  });

  it('uses the current turn verdict instead of a focused artifact verdict from the prior turn', () => {
    const priorVerifiedArtifact = {
      id: 'prior-verified-artifact',
      kind: 'content',
      lifecycle: 'live',
      content: { streaming: false, verifyVerdict: 'pass' },
    };
    const currentTurn = beingPresentationFromStores(mirror({
      lastVerification: { verdict: 'fail', evidenceId: 'current-turn-failure' },
      recentEvents: [
        { id: 1, type: 'turn.started', summary: 'new turn', occurredAt: null, receivedAt: '2026-09-22T00:00:02.000Z' },
        { id: 2, type: 'verification.failed', summary: 'current failure', occurredAt: null, receivedAt: '2026-09-22T00:00:03.000Z' },
      ],
    }), {
      ...tabs,
      tabs: [priorVerifiedArtifact as never],
      focusId: priorVerifiedArtifact.id,
    }, 'complete');

    expect(currentTurn).toMatchObject({ phase: 'recovering', taskState: 'failed', coherence: 'degraded' });
    expect(currentTurn.signals).toContain('verification-fail');
    expect(currentTurn.signals).not.toContain('verification-pass');
  });

  it('keeps the current-turn boundary after its turn.started event ages out of recent history', () => {
    const oldArtifact = {
      id: 'old-verified-artifact',
      kind: 'content',
      lifecycle: 'live',
      content: { streaming: false, verifyVerdict: 'pass' },
    };
    const recentEvents = Array.from({ length: 256 }, (_, index) => ({
      id: index + 2,
      type: 'observation.recorded',
      summary: 'bounded event history',
      occurredAt: null,
      receivedAt: '2026-09-22T00:01:00.000Z',
    }));
    const longTurn = mirror({
      lastTurnStartedEventId: 1,
      lastVerificationEventId: 0,
      lastVerification: { verdict: 'pass', evidenceId: 'prior-turn-pass' },
      recentEvents,
    });

    const current = beingPresentationFromStores(longTurn, {
      ...tabs,
      tabs: [oldArtifact as never],
      focusId: oldArtifact.id,
    }, 'complete');

    expect(current).toMatchObject({ taskState: 'done-unverified', coherence: 'unverified' });
    expect(current.signals).not.toContain('verification-pass');
  });

  it('does not promote a retained receipt when a replay gap invalidated turn attribution', () => {
    const recovered = beingPresentationFromStores(mirror({
      phase: 'idle',
      turnAttributionInvalidated: true,
      lastTurnStartedEventId: 1,
      lastVerificationEventId: 2,
      lastVerification: { verdict: 'pass', evidenceId: 'pre-gap-pass' },
      recentEvents: [
        { id: 1, type: 'turn.started', summary: 'prior turn', occurredAt: null, receivedAt: '2026-09-22T00:00:01.000Z' },
        { id: 2, type: 'verification.passed', summary: 'prior pass', occurredAt: null, receivedAt: '2026-09-22T00:00:02.000Z' },
        { id: 3, type: 'turn.completed', summary: 'prior turn ended', occurredAt: null, receivedAt: '2026-09-22T00:00:03.000Z' },
      ],
    }), tabs, 'complete');

    expect(recovered).toMatchObject({ taskState: 'done-unverified', coherence: 'unverified' });
    expect(recovered.signals).not.toContain('verification-pass');
  });

  it.each([
    ['pass', 'done-verified'],
    ['fail', 'failed'],
  ] as const)('retains the current-turn %s verdict after its event ages out of recent history', (verdict, taskState) => {
    const recentEvents = Array.from({ length: 256 }, (_, index) => ({
      id: index + 3,
      type: 'observation.recorded',
      summary: 'bounded event history',
      occurredAt: null,
      receivedAt: '2026-09-22T00:01:00.000Z',
    }));
    const longTurn = mirror({
      lastTurnStartedEventId: 1,
      lastVerificationEventId: 2,
      lastVerification: { verdict, evidenceId: `current-turn-${verdict}` },
      recentEvents,
    });

    expect(beingPresentationFromStores(longTurn, tabs, 'complete').taskState).toBe(taskState);
  });

  it('accepts a verification event from the current turn for the fallback surface', () => {
    const currentTurn = beingPresentationFromStores(mirror({
      lastVerification: { verdict: 'pass', evidenceId: 'current-result' },
      recentEvents: [
        { id: 1, type: 'turn.started', summary: 'current turn', occurredAt: null, receivedAt: '2026-09-22T00:00:01.000Z' },
        { id: 2, type: 'verification.passed', summary: 'current pass', occurredAt: null, receivedAt: '2026-09-22T00:00:02.000Z' },
      ],
    }), tabs, 'complete');

    expect(currentTurn).toMatchObject({ taskState: 'done-verified', coherence: 'fresh' });
  });

  it('does not carry a prior refusal into the next measured turn', () => {
    const nextTurn = beingPresentationFromStores(mirror({
      recentEvents: [
        { id: 1, type: 'turn.started', summary: 'first', occurredAt: null, receivedAt: '2026-09-22T00:00:00.000Z' },
        { id: 2, type: 'security.refusal.recorded', summary: 'refused', occurredAt: null, receivedAt: '2026-09-22T00:00:01.000Z' },
        { id: 3, type: 'turn.started', summary: 'second', occurredAt: null, receivedAt: '2026-09-22T00:00:02.000Z' },
      ],
    }), tabs);

    expect(nextTurn).toMatchObject({ phase: 'resting', taskState: 'idle', coherence: 'fresh' });
  });

  it('does not carry a prior route label into a new measured turn', () => {
    const nextTurn = beingFactsFromStores(mirror({
      recentEvents: [
        {
          id: 1,
          type: 'route.selected',
          summary: 'local route',
          payload: { privacy: 'local' },
          occurredAt: null,
          receivedAt: '2026-09-22T00:00:00.000Z',
        } as never,
        { id: 2, type: 'turn.started', summary: 'second', occurredAt: null, receivedAt: '2026-09-22T00:00:01.000Z' },
      ],
    }), tabs);

    expect(nextTurn.route).toBe('unknown');
  });

  it('retains a route label when the route event belongs to the current turn', () => {
    const currentTurn = beingFactsFromStores(mirror({
      recentEvents: [
        { id: 1, type: 'turn.started', summary: 'current', occurredAt: null, receivedAt: '2026-09-22T00:00:00.000Z' },
        {
          id: 2,
          type: 'route.selected',
          summary: 'local route',
          payload: { privacy: 'local' },
          occurredAt: null,
          receivedAt: '2026-09-22T00:00:01.000Z',
        } as never,
      ],
    }), tabs);

    expect(currentTurn.route).toBe('local');
  });
});
