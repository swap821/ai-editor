import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import {
  startSwarmPlan,
  markSwarmCloudSubtask,
  resetSwarmHUD,
} from '../superbrain/lib/swarmHUDStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';
import {
  getAuroraState,
  __resetAuroraBridgeForTests,
} from './verifyAuroraBridge';
import {
  getSpineFlashState,
  triggerSpineFlash,
  __resetSpineFlashBridgeForTests,
} from './spineFlashBridge';

vi.mock('@react-three/fiber', () => ({
  useFrame: () => undefined,
  useThree: () => ({ gl: {} }),
}));

vi.mock('@react-three/drei', () => ({
  Line: ({ points, 'data-testid': testId }: { points: unknown[]; 'data-testid'?: string }) => (
    <div data-testid={testId ?? 'line'} data-points={points.length} />
  ),
}));

describe('SuperbrainReactiveEffects', () => {
  beforeEach(() => {
    __resetSpineFusionForTests();
    __resetAuroraBridgeForTests();
    __resetSpineFlashBridgeForTests();
    resetSwarmHUD();
    // Give the fusion bus a deterministic transform so seat math is safe.
    setSpineFusion(1, [0, 0, 0]);
  });

  it('renders no verify aurora at rest', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(getAuroraState().intensity).toBe(0);
    expect(container.querySelector('[data-testid="verify-aurora"]')).toBeNull();
  });

  it('spikes the verify aurora intensity on a verify pass event and renders the bloom', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(getAuroraState().intensity).toBe(0);

    act(() => {
      publishCognition({
        type: 'verify',
        source: 'aios',
        data: { verdict: 'pass', target: 'test.py' },
      });
    });

    expect(getAuroraState().intensity).toBe(1);
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
      const lightning = container.querySelector('[data-testid="line"]');
      expect(lightning).toBeTruthy();
    });
  });

  it('renders a spine-flash bead when the bridge is triggered', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(getSpineFlashState().intensity).toBe(0);

    act(() => {
      triggerSpineFlash();
    });

    expect(getSpineFlashState().intensity).toBe(1);
    await vi.waitFor(() => {
      const flash = container.querySelector('[data-testid="spine-flash"]');
      expect(flash).toBeTruthy();
    });
  });
});
