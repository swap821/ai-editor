import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import {
  startSwarmPlan,
  markSwarmCloudSubtask,
  resetSwarmHUD,
} from '../superbrain/lib/swarmHUDStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';
import {
  getAuroraIntensity,
  __resetAuroraBridgeForTests,
} from './verifyAuroraBridge';

vi.mock('@react-three/fiber', () => ({
  useFrame: () => undefined,
  useThree: () => ({ gl: {} }),
}));

vi.mock('@react-three/drei', () => ({
  Line: ({ points }: { points: unknown[] }) => (
    <div data-testid="lightning" data-points={points.length} />
  ),
}));

describe('SuperbrainReactiveEffects', () => {
  beforeEach(() => {
    __resetSpineFusionForTests();
    __resetAuroraBridgeForTests();
    resetSwarmHUD();
    // Give the fusion bus a deterministic transform so seat math is safe.
    setSpineFusion(1, [0, 0, 0]);
  });

  it('renders no verify aurora at rest', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(getAuroraIntensity()).toBe(0);
    expect(container.querySelector('[data-testid="verify-aurora"]')).toBeNull();
  });

  it('spikes the verify aurora intensity on a verify pass event and renders the bloom', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(getAuroraIntensity()).toBe(0);

    act(() => {
      publishCognition({
        type: 'verify',
        source: 'aios',
        data: { verdict: 'pass', target: 'test.py' },
      });
    });

    expect(getAuroraIntensity()).toBe(1);
    expect(container.querySelector('[data-testid="verify-aurora"]')).not.toBeNull();
  });

  it('renders a lightning element when a cloud_route index is added', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    act(() => {
      startSwarmPlan(['cloud task', 'local task']);
      markSwarmCloudSubtask(0);
    });

    // The component renders lightning asynchronously via state; flush effects.
    await vi.waitFor(() => {
      const lightning = container.querySelector('[data-testid="lightning"]');
      expect(lightning).toBeTruthy();
    });
  });
});
