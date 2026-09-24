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
  Line: ({ 'data-testid': testId }: { 'data-testid'?: string }) => <div data-testid={testId ?? 'line'} />,
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

  it('renders a bounded physical branch alongside the temporary worker marker', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelectorAll('[data-testid="worker-mote"]')).toHaveLength(1);
    expect(view.container.querySelectorAll('[data-testid="worker-branch"]')).toHaveLength(1);
  });

  it('caps a worker burst at eight branches and releases them when the posture clears', async () => {
    mockBeing.current = {
      phase: 'acting',
      taskState: 'working',
      coherence: 'fresh',
      motion: 'conduct',
      attention: 'workspace',
      signals: ['worker-active'],
      workers: Array.from({ length: 12 }, () => 'active'),
    };
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelectorAll('[data-testid="worker-branch"]')).toHaveLength(8);
    expect(view.container.querySelectorAll('[data-testid="worker-mote"]')).toHaveLength(8);

    mockBeing.current = {
      phase: 'resting',
      taskState: 'idle',
      coherence: 'fresh',
      motion: 'calm',
      attention: 'none',
      signals: [],
      workers: [],
    };
    act(() => {
      view.rerender(<SuperbrainReactiveEffects />);
    });
    expect(view.container.querySelectorAll('[data-testid="worker-branch"]')).toHaveLength(0);
    expect(view.container.querySelectorAll('[data-testid="worker-mote"]')).toHaveLength(0);
  });
});
