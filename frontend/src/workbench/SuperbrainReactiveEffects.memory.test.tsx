import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { __resetSpineFusionForTests, setSpineFusion } from '../superbrain/lib/spineFusionBus';
import { derivePhysicalSnapshot } from '../livingMirror/being/physicalSnapshot';
import type { BeingPresentation } from '../livingMirror/being/semanticKernel';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'learning',
    taskState: 'working',
    coherence: 'fresh',
    motion: 'attention',
    attention: 'workspace',
    signals: ['memory-promoted'],
    workers: [],
  } as BeingPresentation,
}));

const mockReducedMotion = vi.hoisted(() => ({ current: false }));

vi.mock('../livingMirror/being/useBeingPresentation', () => ({
  useBeingPresentation: () => mockBeing.current,
}));

vi.mock('../superbrain/lib/reducedMotion', () => ({
  useReducedMotion: () => mockReducedMotion.current,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: () => undefined,
}));

vi.mock('@react-three/drei', () => ({
  Line: ({ 'data-testid': testId }: { 'data-testid'?: string }) => <div data-testid={testId ?? 'line'} />,
}));

describe('SuperbrainReactiveEffects memory projection', () => {
  beforeEach(() => {
    mockReducedMotion.current = false;
    __resetSpineFusionForTests();
    setSpineFusion(1, [0, 0, 0]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a stable promoted memory field as physical evidence', async () => {
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="memory-cerebellar-field"]')).not.toBeNull();
    expect(derivePhysicalSnapshot(mockBeing.current).memory).toEqual({ layer: 'promoted', pulse: 'settle' });
  });

  it('keeps a recalled pulse visible as a bounded static cue', async () => {
    mockBeing.current = {
      phase: 'resting',
      taskState: 'idle',
      coherence: 'fresh',
      motion: 'calm',
      attention: 'none',
      signals: ['memory-recalled'],
      workers: [],
    };
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="memory-cerebellar-field"]')).not.toBeNull();
    expect(derivePhysicalSnapshot(mockBeing.current).memory).toEqual({ layer: 'recalled', pulse: 'inward' });
  });

  it('retains memory meaning when reduced motion is enabled', async () => {
    mockReducedMotion.current = true;
    mockBeing.current = {
      phase: 'reflex',
      taskState: 'working',
      coherence: 'fresh',
      motion: 'conduct',
      attention: 'workspace',
      signals: ['reflex-reused'],
      workers: [],
    };
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="memory-cerebellar-field"]')).not.toBeNull();
    expect(derivePhysicalSnapshot(mockBeing.current).memory).toEqual({ layer: 'reflex', pulse: 'conduct' });
    expect(view.container.querySelector('[data-testid="cortex-posture-field"]')).not.toBeNull();
    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).toBeNull();
  });
});
