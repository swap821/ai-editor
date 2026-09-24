import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { act } from 'react';
import { markSwarmCloudSubtask, resetSwarmHUD, startSwarmPlan } from '../superbrain/lib/swarmHUDStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'stale',
    taskState: 'stale',
    coherence: 'stale',
    motion: 'calm',
    attention: 'none',
    signals: [],
    workers: [],
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
  Line: ({ opacity, 'data-testid': testId }: { opacity?: number; 'data-testid'?: string }) => (
    <div data-testid={testId ?? 'line'} data-opacity={String(opacity ?? 1)} />
  ),
}));

describe('SuperbrainReactiveEffects coherence projection', () => {
  beforeEach(() => {
    mockBeing.current = {
      phase: 'stale',
      taskState: 'stale',
      coherence: 'stale',
      motion: 'calm',
      attention: 'none',
      signals: [],
      workers: [],
    };
    resetSwarmHUD();
    __resetSpineFusionForTests();
    setSpineFusion(1, [0, 0, 0]);
  });

  it('ghosts raw cloud evidence while the measured projection is stale', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    act(() => {
      startSwarmPlan(['cloud task']);
      markSwarmCloudSubtask(0);
    });

    await vi.waitFor(() => {
      const line = container.querySelector('[data-testid="line"]');
      expect(line).not.toBeNull();
      expect(Number(line?.getAttribute('data-opacity'))).toBeCloseTo(0.9 * 0.38, 5);
    });
  });
});
