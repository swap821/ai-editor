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
      'requested', 'admitted', 'active', 'awaiting-capability', 'returned', 'dissolved',
    ]));
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
    expect(facts.workers?.slice(0, 2)).toEqual(['active', 'active']);
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
