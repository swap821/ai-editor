import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'recovering',
    taskState: 'restored',
    coherence: 'fresh',
    motion: 'reabsorb',
    attention: 'none',
    signals: ['worker-returned'],
    workers: ['returned'],
  },
}));

vi.mock('../livingMirror/being/useBeingPresentation', () => ({
  useBeingPresentation: () => mockBeing.current,
}));

vi.mock('../superbrain/lib/reducedMotion', () => ({
  useReducedMotion: () => false,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: () => undefined,
}));

vi.mock('@react-three/drei', () => ({
  Line: () => <div data-testid="line" />,
}));

describe('SuperbrainReactiveEffects worker lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    __resetSpineFusionForTests();
    setSpineFusion(1, [0, 0, 0]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('does not recreate an expired terminal mote from the same retained observation', async () => {
    let now = 1_000;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="worker-mote"]')).not.toBeNull();

    await act(async () => {
      now = 2_600;
      vi.advanceTimersByTime(250);
    });
    expect(view.container.querySelector('[data-testid="worker-mote"]')).toBeNull();

    act(() => {
      view.rerender(<SuperbrainReactiveEffects />);
    });
    expect(view.container.querySelector('[data-testid="worker-mote"]')).toBeNull();
  });
});
