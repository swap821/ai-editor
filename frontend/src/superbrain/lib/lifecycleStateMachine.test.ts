import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  LifecycleState,
  ArrivalMode,
  deriveNextState,
  getElapsedInState,
  __resetLifecycleForTests,
  getLifecycleSnapshot,
  subscribeLifecycle,
  transitionToArriving,
  notifyDirective,
  tickLifecycle,
  DEFAULT_LIFECYCLE_CONFIG,
  type LifecycleSnapshot,
} from './lifecycleStateMachine';

const baseSnapshot = (over: Partial<LifecycleSnapshot> = {}): LifecycleSnapshot => ({
  state: LifecycleState.REST,
  arrivalMode: undefined,
  elapsedInState: 0,
  lastTransitionAt: 0,
  directiveCount: 0,
  ...over,
});

describe('deriveNextState (pure)', () => {
  const cfg = DEFAULT_LIFECYCLE_CONFIG;

  it('BOOTING stays BOOTING until an explicit transition', () => {
    const r = deriveNextState(1000, baseSnapshot({ state: LifecycleState.BOOTING }), null, cfg);
    expect(r.state).toBe(LifecycleState.BOOTING);
  });

  it('ARRIVING -> REST after arrivalDurationMs', () => {
    const snap = baseSnapshot({ state: LifecycleState.ARRIVING, lastTransitionAt: 0, arrivalMode: ArrivalMode.COALESCENCE });
    const r = deriveNextState(cfg.arrivalDurationMs + 1, snap, null, cfg);
    expect(r.state).toBe(LifecycleState.REST);
  });

  it('ARRIVING stays ARRIVING before the duration (cinematic priority, ignores directive)', () => {
    const snap = baseSnapshot({ state: LifecycleState.ARRIVING, lastTransitionAt: 0 });
    const r = deriveNextState(500, snap, { type: 'directive' }, cfg);
    expect(r.state).toBe(LifecycleState.ARRIVING);
  });

  it('REST -> ATTENTIVE on a directive event', () => {
    const r = deriveNextState(1000, baseSnapshot(), { type: 'directive' }, cfg);
    expect(r.state).toBe(LifecycleState.ATTENTIVE);
  });

  it('REST ignores ambient events', () => {
    const r = deriveNextState(1000, baseSnapshot(), { type: 'burst' }, cfg);
    expect(r.state).toBe(LifecycleState.REST);
  });

  it('ATTENTIVE -> REST after attentiveDecayMs of silence', () => {
    const snap = baseSnapshot({ state: LifecycleState.ATTENTIVE, lastTransitionAt: 0 });
    const r = deriveNextState(cfg.attentiveDecayMs + 1, snap, null, cfg);
    expect(r.state).toBe(LifecycleState.REST);
  });
});

describe('getElapsedInState', () => {
  it('returns now minus lastTransitionAt', () => {
    expect(getElapsedInState(1500, baseSnapshot({ lastTransitionAt: 500 }))).toBe(1000);
  });
});

describe('singleton + subscribers', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    __resetLifecycleForTests();
  });

  it('starts in BOOTING and notifies new subscribers immediately', () => {
    const seen: LifecycleState[] = [];
    const unsub = subscribeLifecycle((s) => seen.push(s.state));
    expect(seen).toEqual([LifecycleState.BOOTING]);
    unsub();
  });

  it('transitionToArriving moves to ARRIVING with the given mode', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.ARRIVING);
    expect(getLifecycleSnapshot().arrivalMode).toBe(ArrivalMode.COALESCENCE);
  });

  it('arriving auto-settles to REST after the duration on tick', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    vi.setSystemTime(DEFAULT_LIFECYCLE_CONFIG.arrivalDurationMs + 10);
    tickLifecycle();
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.REST);
  });

  it('a directive in REST wakes the being to ATTENTIVE and counts it', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    vi.setSystemTime(DEFAULT_LIFECYCLE_CONFIG.arrivalDurationMs + 10);
    tickLifecycle();
    notifyDirective();
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.ATTENTIVE);
    expect(getLifecycleSnapshot().directiveCount).toBe(1);
  });

  it('notifyDirective during ARRIVING does not reset the timer or wake the being', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    const t0 = getLifecycleSnapshot().lastTransitionAt;
    notifyDirective();
    expect(getLifecycleSnapshot().lastTransitionAt).toBe(t0);
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.ARRIVING);
    expect(getLifecycleSnapshot().directiveCount).toBe(0);
  });
});
