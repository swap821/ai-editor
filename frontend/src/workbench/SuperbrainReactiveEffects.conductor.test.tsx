import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import {
  __resetTabStoreForTests,
  showApprovalSurface,
  showContentSurface,
} from '../superbrain/lib/tabStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';
import { QualityTierProvider } from '../superbrain/components/QualityTierProvider';
import { derivePhysicalSnapshot } from '../livingMirror/being/physicalSnapshot';
import type { BeingPresentation } from '../livingMirror/being/semanticKernel';

const mockBeing = vi.hoisted(() => ({
  current: {
    phase: 'resting',
    taskState: 'idle',
    coherence: 'fresh',
    motion: 'calm',
    attention: 'none',
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
  Line: ({
    'data-testid': testId,
    'data-held': held,
    'data-stopped': stopped,
    points,
  }: { 'data-testid'?: string; 'data-held'?: string; 'data-stopped'?: string; points?: unknown[] }) => (
    <div
      data-testid={testId ?? 'line'}
      data-held={held}
      data-stopped={stopped}
      data-points={points?.length}
    />
  ),
}));

describe('SuperbrainReactiveEffects point conductor', () => {
  beforeEach(() => {
    __resetTabStoreForTests();
    __resetSpineFusionForTests();
    setSpineFusion(1, [0, 0, 0]);
  });

  afterEach(() => {
    __resetTabStoreForTests();
  });

  it('renders a bounded conducting path and active seat for a live workspace', async () => {
    showContentSurface(
      { code: 'export const answer = 42;', language: 'typescript', filepath: 'answer.ts' },
      { seatIndex: 3 },
    );
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).not.toBeNull();
    expect(view.container.querySelectorAll('[data-testid="cortex-current"]').length).toBeGreaterThan(0);
    expect(view.container.querySelectorAll('[data-testid="physical-conductor-seat"]')).toHaveLength(1);
    expect(derivePhysicalSnapshot(mockBeing.current).conductor.posture).toBe('idle');
  });

  it('holds the conductor at the sovereign boundary for approval', async () => {
    showApprovalSurface(
      {
        requestRef: 'approval-test',
        summary: 'Approval required',
        explanation: 'Test approval',
        diff: '+answer',
        command: '',
        kindLabel: 'create',
        filepath: 'answer.ts',
        content: 'export const answer = 42;',
      },
      { seatIndex: 2 },
    );
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="physical-conductor-seat"]')).not.toBeNull();
    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).not.toBeNull();
    expect(derivePhysicalSnapshot({ ...mockBeing.current, taskState: 'needs-permission' }).conductor.posture).toBe('held');
  });

  it('keeps the conductor visible on the low tier with a reduced geometry budget', async () => {
    window.localStorage.removeItem('gag-quality-tier-v3');
    showContentSurface(
      { code: 'export const answer = 42;', language: 'typescript', filepath: 'low.ts' },
      { seatIndex: 1 },
    );
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(
      <QualityTierProvider defaultTier="low">
        <SuperbrainReactiveEffects />
      </QualityTierProvider>,
    );

    expect(view.container.querySelector('[data-testid="physical-conductor-seat"]')).not.toBeNull();
  });
});
