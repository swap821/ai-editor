import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { act } from 'react';
import { getSwarmHUDState, startSwarmPlan, markSwarmCloudSubtask, resetSwarmHUD } from '../superbrain/lib/swarmHUDStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'stopped',
    taskState: 'stopped',
    coherence: 'stopped',
    motion: 'stop',
    attention: 'none',
    signals: ['emergency-stop'],
    workers: [],
  },
}));

vi.mock('../livingMirror/being/useBeingPresentation', () => ({
  useBeingPresentation: () => mockBeing.current,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: () => undefined,
}));

vi.mock('@react-three/drei', () => ({
  Line: ({ points, 'data-testid': testId }: { points: unknown[]; 'data-testid'?: string }) => (
    <div data-testid={testId ?? 'line'} data-points={points.length} />
  ),
}));

describe('SuperbrainReactiveEffects Emergency Stop boundary', () => {
  beforeEach(() => {
    resetSwarmHUD();
    __resetSpineFusionForTests();
    setSpineFusion(1, [0, 0, 0]);
  });

  it('does not render new cloud-route action lightning while stopped', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    act(() => {
      startSwarmPlan(['cloud task']);
      markSwarmCloudSubtask(0);
    });

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });
    expect(getSwarmHUDState().cloudIndices).toEqual([0]);
    expect(container.querySelector('[data-testid="line"]')).toBeNull();
  });
});
