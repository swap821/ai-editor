import { describe, expect, it } from 'vitest';
import {
  createTurnMetabolismSignals,
  deriveTurnMetabolismSnapshot,
  reduceTurnMetabolismEvent,
} from './turnMetabolism';

const NOW = 10_000;

describe('turnMetabolism', () => {
  it('rests when no cognition event has stamped the body', () => {
    const snapshot = deriveTurnMetabolismSnapshot(createTurnMetabolismSignals(), NOW);

    expect(snapshot).toMatchObject({
      phase: 'rest',
      intensity: 0,
      surfaceExcitation: 0,
      rootExcitation: 0,
      held: false,
    });
  });

  it('maps directive and route signals to thinking metabolism', () => {
    let signals = createTurnMetabolismSignals();
    signals = reduceTurnMetabolismEvent(signals, { type: 'directive', label: 'build' }, NOW);
    signals = reduceTurnMetabolismEvent(signals, { type: 'route', label: 'ACTIVE BRAIN' }, NOW + 100);

    const snapshot = deriveTurnMetabolismSnapshot(signals, NOW + 300);

    expect(snapshot.phase).toBe('thinking');
    expect(snapshot.surfaceExcitation).toBeGreaterThan(0);
    expect(snapshot.rootExcitation).toBeGreaterThan(0);
    expect(snapshot.tint).toBe('#8af5ff');
  });

  it('lets real tool work outrank a recent thinking signal', () => {
    let signals = createTurnMetabolismSignals();
    signals = reduceTurnMetabolismEvent(signals, { type: 'directive' }, NOW);
    signals = reduceTurnMetabolismEvent(
      signals,
      { type: 'agent-dispatch', detail: 'tool engaged: pytest', label: 'PYTEST' },
      NOW + 500,
    );

    const snapshot = deriveTurnMetabolismSnapshot(signals, NOW + 800);

    expect(snapshot.phase).toBe('working');
    expect(snapshot.rootExcitation).toBeGreaterThan(snapshot.surfaceExcitation);
    expect(snapshot.breathGain).toBeGreaterThan(0.2);
  });

  it('holds approval until an approval resolution event arrives', () => {
    let signals = createTurnMetabolismSignals();
    signals = reduceTurnMetabolismEvent(signals, { type: 'approval-required', label: 'hold' }, NOW);

    const held = deriveTurnMetabolismSnapshot(signals, NOW + 60_000);
    expect(held.phase).toBe('approval');
    expect(held.held).toBe(true);
    expect(held.breathGain).toBeLessThan(0);

    signals = reduceTurnMetabolismEvent(signals, { type: 'approval-resolved', label: 'approved' }, NOW + 60_500);
    const settled = deriveTurnMetabolismSnapshot(signals, NOW + 60_600);
    expect(settled.phase).toBe('settling');
    expect(settled.held).toBe(false);
  });

  it('maps cognition faults, rejected approvals, and verification red to error metabolism', () => {
    const fault = reduceTurnMetabolismEvent(
      createTurnMetabolismSignals(),
      { type: 'synthesis', label: 'COGNITION FAULT', detail: 'backend error' },
      NOW,
    );
    const rejected = reduceTurnMetabolismEvent(
      createTurnMetabolismSignals(),
      { type: 'approval-resolved', label: 'rejected' },
      NOW,
    );
    const red = reduceTurnMetabolismEvent(
      createTurnMetabolismSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION RED' },
      NOW,
    );

    expect(deriveTurnMetabolismSnapshot(fault, NOW + 100).phase).toBe('error');
    expect(deriveTurnMetabolismSnapshot(rejected, NOW + 100).phase).toBe('error');
    expect(deriveTurnMetabolismSnapshot(red, NOW + 100).phase).toBe('error');
  });

  it('decays stale events back to rest', () => {
    let signals = createTurnMetabolismSignals();
    signals = reduceTurnMetabolismEvent(signals, { type: 'agent-dispatch' }, NOW);

    expect(deriveTurnMetabolismSnapshot(signals, NOW + 3601).phase).toBe('rest');
  });
});
