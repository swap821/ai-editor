import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { act } from 'react';
import { markSwarmCloudSubtask, resetSwarmHUD, startSwarmPlan } from '../superbrain/lib/swarmHUDStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';
import { getSpineFlashState, triggerSpineFlash, __resetSpineFlashBridgeForTests } from './spineFlashBridge';
import { getAuroraState, __resetAuroraBridgeForTests } from './verifyAuroraBridge';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'acting',
    taskState: 'working',
    coherence: 'fresh',
    motion: 'conduct',
    attention: 'workspace',
    signals: ['worker-active'],
    workers: ['active'],
  },
}));

vi.mock('../livingMirror/being/useBeingPresentation', () => ({
  useBeingPresentation: () => mockBeing.current,
}));

vi.mock('../superbrain/lib/reducedMotion', () => ({
  useReducedMotion: () => true,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: () => undefined,
}));

vi.mock('@react-three/drei', () => ({
  Line: ({ 'data-testid': testId }: { 'data-testid'?: string }) => <div data-testid={testId ?? 'line'} />,
}));

describe('SuperbrainReactiveEffects reduced-motion boundary', () => {
  beforeEach(() => {
    resetSwarmHUD();
    __resetSpineFusionForTests();
    __resetSpineFlashBridgeForTests();
    __resetAuroraBridgeForTests();
    setSpineFusion(1, [0, 0, 0]);
  });

  it('omits product-owned travel and bloom effects while retaining the semantic seam', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const { container } = render(<SuperbrainReactiveEffects />);

    act(() => {
      startSwarmPlan(['cloud task']);
      markSwarmCloudSubtask(0);
      triggerSpineFlash();
    });

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });

    expect(getSpineFlashState()).toMatchObject({ intensity: 1, progress: 0 });
    expect(getAuroraState().intensity).toBe(0);
    expect(container.querySelector('[data-testid="line"]')).toBeNull();
    expect(container.querySelector('[data-testid="spine-flash"]')).toBeNull();
    expect(container.querySelector('[data-testid="cortex-posture-field"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="cortex-current"]')).not.toBeNull();
  });
});
