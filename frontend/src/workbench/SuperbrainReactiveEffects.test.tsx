import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { act } from 'react';
import {
  startSwarmPlan,
  markSwarmCloudSubtask,
  resetSwarmHUD,
} from '../superbrain/lib/swarmHUDStore';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
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
    useMirrorStore.setState({
      lastEventId: null,
      lastTurnStartedEventId: null,
      lastVerificationEventId: null,
      lastVerification: null,
      recentEvents: [],
      workers: {},
      approvalRequired: false,
    });
    // Give the fusion bus a deterministic transform so seat math is safe.
    setSpineFusion(1, [0, 0, 0]);
  });

  it('renders no verify aurora at rest', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(container.querySelector('[data-testid="cortex-posture-field"]')).not.toBeNull();
    expect(getAuroraState().intensity).toBe(0);
    expect(container.querySelector('[data-testid="verify-aurora"]')).toBeNull();
  });

  it('spikes the verify aurora from an admitted mirror verification and renders the bloom', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    expect(getAuroraState().intensity).toBe(0);

    act(() => {
      useMirrorStore.getState().applyEvent(1, 'verification.passed', {
        verdict: 'pass',
        target: 'test.py',
      });
    });

    await vi.waitFor(() => {
      expect(getAuroraState().intensity).toBe(1);
      expect(container.querySelector('[data-testid="verify-aurora"]')).not.toBeNull();
    });
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
      expect(flash).toHaveAttribute('data-points', '9');
    });
  });
});
