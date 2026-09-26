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
    workers: [{ workerId: 'worker-returned', state: 'returned', cursor: 1 }],
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
      workers: Array.from({ length: 12 }, (_, index) => ({
        workerId: `worker-${index}`,
        state: 'active' as const,
        cursor: index,
      })),
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

  it('keeps each worker in its assigned scene seat when the roster reorders and grows', async () => {
    const presentation = (workers: Array<{ workerId: string; state: 'active'; cursor: number }>) => ({
      phase: 'acting' as const,
      taskState: 'working' as const,
      coherence: 'fresh' as const,
      motion: 'conduct' as const,
      attention: 'workspace' as const,
      signals: ['worker-active' as const],
      workers,
    });
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects presentationOverride={presentation([
      { workerId: 'worker-alpha', state: 'active', cursor: 1 },
      { workerId: 'worker-beta', state: 'active', cursor: 2 },
    ])} />);

    expect(view.container.querySelector('group[name="worker-seat-0"]')).not.toBeNull();
    expect(view.container.querySelector('group[name="worker-seat-1"]')).not.toBeNull();

    view.rerender(<SuperbrainReactiveEffects presentationOverride={presentation([
      { workerId: 'worker-gamma', state: 'active', cursor: 3 },
      { workerId: 'worker-beta', state: 'active', cursor: 2 },
      { workerId: 'worker-alpha', state: 'active', cursor: 1 },
    ])} />);

    expect(view.container.querySelector('group[name="worker-seat-0"]')).not.toBeNull();
    expect(view.container.querySelector('group[name="worker-seat-1"]')).not.toBeNull();
    expect(view.container.querySelector('group[name="worker-seat-2"]')).not.toBeNull();
  });
});
