import { describe, expect, it } from 'vitest';
import {
  COMPLETION_HOLD_WINDOW_MS,
  COMPLETION_REABSORB_AFTER_MS,
  createCompletionReflexSignals,
  deriveCompletionReflexSnapshot,
  markCompletionReflexSignalsReabsorbing,
  reduceCompletionReflexEvent,
} from './completionReflex';
import type { MaterializedTabRecord } from './tabStore';

const NOW = 32_000;

const contentTab: MaterializedTabRecord = {
  id: 'content-1',
  kind: 'content',
  lifecycle: 'live',
  originLocal: [0, 0.2, 0.5],
  targetLocal: [1.1, 0.2, 0.6],
  seatIndex: 3,
  content: { code: 'print(1)', language: 'python', filepath: 'demo.py' },
  input: null,
  approval: null,
  bornAt: NOW - 4000,
  phaseStartedAt: NOW - 2500,
};

const inputTab: MaterializedTabRecord = {
  ...contentTab,
  id: 'input-1',
  kind: 'input',
  content: null,
  input: { text: 'build' },
};

describe('completionReflex', () => {
  it('rests before an outcome lands on a workspace', () => {
    const reflex = deriveCompletionReflexSnapshot(createCompletionReflexSignals(), NOW);

    expect(reflex).toMatchObject({
      state: 'idle',
      intensity: 0,
      reabsorbReady: false,
      hold: false,
    });
  });

  it('turns verification green into a delayed reabsorption contract', () => {
    const signals = reduceCompletionReflexEvent(
      createCompletionReflexSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION GREEN', detail: 'vitest passed' },
      contentTab,
      NOW,
    );

    const settling = deriveCompletionReflexSnapshot(signals, NOW + 500);
    const ready = deriveCompletionReflexSnapshot(signals, NOW + COMPLETION_REABSORB_AFTER_MS + 1);

    expect(settling.state).toBe('settling');
    expect(settling.targetId).toBe(contentTab.id);
    expect(settling.targetSeatIndex).toBe(3);
    expect(settling.settleProgress).toBeGreaterThan(0);
    expect(settling.reabsorbReady).toBe(false);
    expect(ready.reabsorbReady).toBe(true);
    expect(ready.beadProgress).toBeGreaterThan(settling.beadProgress);
  });

  it('marks issued reabsorption once so the layer does not repeat the command', () => {
    let signals = reduceCompletionReflexEvent(
      createCompletionReflexSignals(),
      { type: 'knowledge-acquired', label: 'SKILL MASTERED' },
      contentTab,
      NOW,
    );

    signals = markCompletionReflexSignalsReabsorbing(signals, contentTab.id, NOW + COMPLETION_REABSORB_AFTER_MS + 40);
    const snapshot = deriveCompletionReflexSnapshot(signals, NOW + COMPLETION_REABSORB_AFTER_MS + 80);

    expect(snapshot.state).toBe('reabsorbing');
    expect(snapshot.reabsorbReady).toBe(false);
    expect(snapshot.memoryOpacity).toBeGreaterThan(0);
  });

  it('turns verification red into a correction hold instead of a dissolve', () => {
    const signals = reduceCompletionReflexEvent(
      createCompletionReflexSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION RED', detail: 'test failed' },
      contentTab,
      NOW,
    );

    const held = deriveCompletionReflexSnapshot(signals, NOW + 700);
    const stale = deriveCompletionReflexSnapshot(signals, NOW + COMPLETION_HOLD_WINDOW_MS + 1);

    expect(held.state).toBe('held');
    expect(held.hold).toBe(true);
    expect(held.reabsorbReady).toBe(false);
    expect(held.tint).toBe('#ff5f7a');
    expect(stale.state).toBe('idle');
  });

  it('ignores outcomes when only the intake surface is focused', () => {
    const signals = reduceCompletionReflexEvent(
      createCompletionReflexSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION GREEN' },
      inputTab,
      NOW,
    );

    expect(deriveCompletionReflexSnapshot(signals, NOW + 500).state).toBe('idle');
  });

  it('clears a stale reflex when a new directive starts', () => {
    let signals = reduceCompletionReflexEvent(
      createCompletionReflexSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION GREEN' },
      contentTab,
      NOW,
    );
    signals = reduceCompletionReflexEvent(signals, { type: 'directive', label: 'new work' }, contentTab, NOW + 600);

    expect(deriveCompletionReflexSnapshot(signals, NOW + 700).state).toBe('idle');
  });
});
