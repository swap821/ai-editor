import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { __resetSpineFusionForTests, setSpineFusion } from '../superbrain/lib/spineFusionBus';
import { derivePhysicalSnapshot } from '../livingMirror/being/physicalSnapshot';
import type { BeingPresentation } from '../livingMirror/being/semanticKernel';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'verifying',
    taskState: 'checking',
    coherence: 'fresh',
    motion: 'verify',
    attention: 'workspace',
    signals: [],
    workers: [],
  } as BeingPresentation,
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
  Line: ({ 'data-testid': testId, points }: { 'data-testid'?: string; points?: unknown[] }) => (
    <div data-testid={testId ?? 'line'} data-points={points?.length} />
  ),
}));

describe('SuperbrainReactiveEffects verification and council projections', () => {
  beforeEach(() => {
    __resetSpineFusionForTests();
    setSpineFusion(1, [0, 0, 0]);
    mockBeing.current = {
      phase: 'verifying',
      taskState: 'checking',
      coherence: 'fresh',
      motion: 'verify',
      attention: 'workspace',
      signals: [],
      workers: [],
    };
  });

  it('renders a bounded verification field while truth is unsettled', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="verification-field"]')).not.toBeNull();
    expect(derivePhysicalSnapshot(mockBeing.current).verification).toEqual({
      state: 'pending',
      settlement: 'unsettled',
    });
  });

  it('keeps pass and fail physically distinct without upgrading failure to settlement', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    mockBeing.current = {
      ...mockBeing.current,
      phase: 'resting',
      taskState: 'done-verified',
      motion: 'calm',
      signals: ['verification-pass'],
    };
    view.rerender(<SuperbrainReactiveEffects />);
    expect(view.container.querySelector('[data-testid="verification-field"]')).not.toBeNull();
    expect(derivePhysicalSnapshot(mockBeing.current).verification).toEqual({ state: 'pass', settlement: 'stable' });

    mockBeing.current = {
      ...mockBeing.current,
      phase: 'recovering',
      taskState: 'failed',
      coherence: 'degraded',
      motion: 'reabsorb',
      signals: ['verification-fail'],
    };
    view.rerender(<SuperbrainReactiveEffects />);
    expect(view.container.querySelector('[data-testid="verification-field"]')).not.toBeNull();
    expect(derivePhysicalSnapshot(mockBeing.current).verification).toEqual({ state: 'fail', settlement: 'unsettled' });
  });

  it('renders measured council dissent as a bounded internal topology', async () => {
    mockBeing.current = {
      phase: 'planning',
      taskState: 'preparing',
      coherence: 'fresh',
      motion: 'attention',
      attention: 'workspace',
      signals: ['council-dissent'],
      workers: [],
    };
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelectorAll('[data-testid="council-dissent"]').length).toBeGreaterThan(0);
    expect(view.container.querySelectorAll('[data-testid="council-dissent"]').length).toBeLessThanOrEqual(3);
  });
});
