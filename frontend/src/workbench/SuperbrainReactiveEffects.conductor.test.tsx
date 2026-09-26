import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import {
  beginRetractingMaterializedTab,
  __resetTabStoreForTests,
  getTabStoreSnapshot,
  showApprovalSurface,
  showContentSurface,
  type TabSnapshot,
} from '../superbrain/lib/tabStore';
import { setSpineFusion, __resetSpineFusionForTests } from '../superbrain/lib/spineFusionBus';
import { QualityTierProvider } from '../superbrain/components/QualityTierProvider';
import { SEGMENT_ANCHORS } from '../superbrain/lib/spineAnatomy';
import { getBrainDockScale, getCortexAnchor } from '../superbrain/lib/spineFusionBus';
import { CORTEX_COMPOSER_INTAKE_LOCAL, deriveCortexAttentionPaths } from './cortexAttentionPaths';
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
    opacity,
    lineWidth,
    depthTest,
    renderOrder,
    color,
    points,
  }: { 'data-testid'?: string; 'data-held'?: string; 'data-stopped'?: string; 'data-opacity'?: number; 'data-line-width'?: number; 'data-depth-test'?: boolean; 'data-render-order'?: number; opacity?: number; lineWidth?: number; depthTest?: boolean; renderOrder?: number; color?: string; points?: unknown[] }) => (
    <div
      data-testid={testId ?? 'line'}
      data-held={held}
      data-stopped={stopped}
      data-opacity={opacity}
      data-line-width={lineWidth}
      data-depth-test={depthTest}
      data-render-order={renderOrder}
      data-color={color}
      data-points={points?.length}
      data-coordinates={JSON.stringify(points?.map((point) => {
        const candidate = point as { toArray?: () => number[] };
        return candidate.toArray ? candidate.toArray() : point;
      }))}
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

  it('aims cortical currents toward the focused workspace seat', async () => {
    showContentSurface(
      { code: 'export const answer = 42;', language: 'typescript', filepath: 'answer.ts' },
      { seatIndex: 3 },
    );
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).not.toBeNull();
    const dormantPulse = view.container.querySelector('mesh[name="cortex-attention-pulse"]') as (Element & { visible?: boolean }) | null;
    expect(dormantPulse).not.toBeNull();
    expect(dormantPulse?.visible).toBe(false);
    const current = view.container.querySelector('[data-testid="cortex-current"]');
    expect(current).not.toBeNull();
    const coordinates = JSON.parse(current?.getAttribute('data-coordinates') ?? '[]') as number[][];
    const cortex = getCortexAnchor();
    const seat = SEGMENT_ANCHORS[3];
    const aim = [seat.x - cortex[0], seat.y - cortex[1], seat.z - cortex[2]];
    const pathDirection = coordinates[1].map((value, index) => value - coordinates[0][index]);
    const dot = pathDirection.reduce((sum, value, index) => sum + value * aim[index], 0);
    const cosine = dot / (Math.hypot(...pathDirection) * Math.hypot(...aim));
    expect(cosine).toBeGreaterThan(0.95);
    expect(view.container.querySelectorAll('[data-testid="physical-conductor-seat"]')).toHaveLength(1);
    expect(derivePhysicalSnapshot(mockBeing.current).conductor.posture).toBe('idle');
  });

  it('aims at the focused DOM workspace panel instead of a background materialized tab', async () => {
    const fixture: TabSnapshot = {
      tabs: [{
        id: 'background-workspace',
        kind: 'content',
        lifecycle: 'live',
        originLocal: [0, 0.26, 0.48],
        targetLocal: [1.18, 0.22, 0.58],
        seatIndex: 3,
        content: { code: '// background', language: 'text', filepath: 'background.txt' },
        input: null,
        approval: null,
        bornAt: 0,
        phaseStartedAt: 0,
      }],
      focusId: 'focused-dom-workspace',
      attention: null,
      panels: [{
        id: 'focused-dom-workspace',
        title: 'Focused workspace',
        kind: 'fixture',
        seatIndex: 6,
        open: true,
        pinned: false,
      }],
    };
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects tabSnapshotOverride={fixture} />);

    const currents = view.container.querySelectorAll('[data-testid="cortex-current"]');
    expect(currents).toHaveLength(3);
    const coordinates = JSON.parse(currents[1].getAttribute('data-coordinates') ?? '[]') as number[][];
    const cortex = getCortexAnchor();
    const dockScale = getBrainDockScale();
    const origin = cortex.map((value) => value * dockScale) as [number, number, number];
    const focusedSeat = SEGMENT_ANCHORS[6].clone().multiplyScalar(dockScale).toArray() as [number, number, number];
    const expectedPath = deriveCortexAttentionPaths({
      origin,
      target: focusedSeat,
      activity: 0.18,
      convergence: 0.22,
      count: 3,
    })[1];

    expect(coordinates[2][0]).toBeCloseTo(expectedPath[2][0], 8);
    expect(coordinates[2][1]).toBeCloseTo(expectedPath[2][1], 8);
    expect(coordinates[2][2]).toBeCloseTo(expectedPath[2][2], 8);
  });

  it('redirects cortical attention to the intake while a human draft is present', async () => {
    showContentSurface(
      { code: 'export const answer = 42;', language: 'typescript', filepath: 'answer.ts' },
      { seatIndex: 11 },
    );
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects inputDraftPresent />);

    const currents = view.container.querySelectorAll('[data-testid="cortex-current"]');
    expect(currents).toHaveLength(1);
    const current = currents[0];
    const coordinates = JSON.parse(current?.getAttribute('data-coordinates') ?? '[]') as number[][];
    const intake = CORTEX_COMPOSER_INTAKE_LOCAL.map((value) => value * getBrainDockScale());

    expect(coordinates[2][0]).toBeCloseTo(intake[0], 8);
    expect(coordinates[2][1]).toBeCloseTo(intake[1], 8);
    expect(coordinates[2][2]).toBeCloseTo(intake[2], 8);
    expect(current?.getAttribute('data-color')).toBe('#7bf5fb');
    expect(Number(current?.getAttribute('data-opacity'))).toBeGreaterThan(0.85);
    expect(Number(current?.getAttribute('data-line-width'))).toBeGreaterThan(2.5);
    expect(current?.getAttribute('data-depth-test')).toBe('false');
    expect(Number(current?.getAttribute('data-render-order'))).toBeGreaterThan(0);
    const returningPulse = view.container.querySelector('mesh[name="cortex-attention-pulse"]') as (Element & { visible?: boolean }) | null;
    expect(returningPulse?.visible).toBe(true);
    view.rerender(<SuperbrainReactiveEffects />);
    expect(view.container.querySelector('mesh[name="cortex-attention-pulse"]')).toBe(returningPulse);
    expect(returningPulse?.visible).toBe(true);
    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).not.toBeNull();
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

  it('routes body attention to a held approval seat without changing workspace focus', async () => {
    const work = showContentSurface(
      { code: 'export const answer = 42;', language: 'typescript', filepath: 'answer.ts' },
      { seatIndex: 3 },
    );
    showApprovalSurface(
      {
        requestRef: 'approval-test',
        summary: 'Approval required',
        explanation: 'Needs operator consent',
        diff: '+answer',
        command: '',
        kindLabel: 'edit',
        filepath: 'answer.ts',
        content: '',
      },
      { seatIndex: 6 },
    );
    mockBeing.current = {
      ...mockBeing.current,
      phase: 'awaiting-human',
      taskState: 'needs-permission',
      motion: 'attention',
      attention: 'approval',
    };

    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects />);

    expect(getTabStoreSnapshot().focusId).toBe(work.id);
    const currents = view.container.querySelectorAll('[data-testid="cortex-current"]');
    expect(currents.length).toBeGreaterThan(0);
    expect([...currents].every((current) => current.getAttribute('data-color') === '#ffb06e')).toBe(true);
    const scale = getBrainDockScale();
    const expectedSeat = SEGMENT_ANCHORS[6].clone().multiplyScalar(scale).toArray();
    const cortex = getCortexAnchor().map((value) => value * scale) as [number, number, number];
    const physical = derivePhysicalSnapshot(mockBeing.current);
    const expectedAttentionPath = deriveCortexAttentionPaths({
      origin: cortex,
      target: expectedSeat,
      activity: physical.cortex.activity,
      convergence: physical.cortex.convergence,
      count: currents.length,
    })[Math.floor(currents.length / 2)];
    const pathCoordinates = JSON.parse(currents[Math.floor(currents.length / 2)].getAttribute('data-coordinates') ?? '[]') as number[][];
    expect(pathCoordinates[2][0]).toBeCloseTo(expectedAttentionPath[2][0], 8);
    expect(pathCoordinates[2][1]).toBeCloseTo(expectedAttentionPath[2][1], 8);
    expect(pathCoordinates[2][2]).toBeCloseTo(expectedAttentionPath[2][2], 8);

    const conductor = view.container.querySelector('[data-testid="physical-conductor-path"]');
    const conductorCoordinates = JSON.parse(conductor?.getAttribute('data-coordinates') ?? '[]') as number[][];
    const conductorEndpoint = conductorCoordinates[conductorCoordinates.length - 1];
    expect(conductorEndpoint?.[0]).toBeCloseTo(expectedSeat[0], 8);
    expect(conductorEndpoint?.[1]).toBeCloseTo(expectedSeat[1], 8);
    expect(conductorEndpoint?.[2]).toBeCloseTo(expectedSeat[2], 8);

    const firstApproval = getTabStoreSnapshot().tabs.find((tab) => tab.kind === 'approval');
    expect(firstApproval).toBeDefined();
    beginRetractingMaterializedTab(firstApproval!.id);
    mockBeing.current = {
      ...mockBeing.current,
      phase: 'acting',
      taskState: 'working',
      motion: 'conduct',
      attention: 'workspace',
    };
    view.rerender(<SuperbrainReactiveEffects />);

    const replayedApproval = showApprovalSurface(
      {
        requestRef: 'approval-replay',
        summary: 'Approval required for the next step',
        explanation: 'The authorized replay encountered another gated action.',
        diff: '+next step',
        command: '',
        kindLabel: 'edit',
        filepath: 'answer.ts',
        content: '',
      },
      { seatIndex: 6 },
    );
    expect(replayedApproval.id).toBe(firstApproval!.id);
    mockBeing.current = {
      ...mockBeing.current,
      phase: 'awaiting-human',
      taskState: 'needs-permission',
      motion: 'attention',
      attention: 'approval',
    };
    view.rerender(<SuperbrainReactiveEffects />);
    expect([...view.container.querySelectorAll('[data-testid="cortex-current"]')]
      .every((current) => current.getAttribute('data-color') === '#ffb06e')).toBe(true);

    beginRetractingMaterializedTab(replayedApproval.id);
    mockBeing.current = {
      ...mockBeing.current,
      phase: 'acting',
      taskState: 'working',
      motion: 'conduct',
      attention: 'workspace',
    };
    view.rerender(<SuperbrainReactiveEffects />);
    expect(view.container.querySelector('[data-testid="cortex-current"]')?.getAttribute('data-color')).toBe('#54f0a0');

    __resetTabStoreForTests();
    mockBeing.current = {
      ...mockBeing.current,
      phase: 'resting',
      taskState: 'idle',
      motion: 'calm',
      attention: 'none',
    };
    view.rerender(<SuperbrainReactiveEffects />);
    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).toBeNull();
    expect(view.container.querySelector('[data-testid="cortex-current"]')?.getAttribute('data-color')).toBe('#7bf5fb');
  });

  it('renders a gallery workspace fixture without mutating the live tab store', async () => {
    const fixture: TabSnapshot = {
      tabs: [{
        id: 'visual-only-workspace',
        kind: 'content',
        lifecycle: 'live',
        originLocal: [0, 0.26, 0.48],
        targetLocal: [1.18, 0.22, 0.58],
        seatIndex: 4,
        content: { code: '// fixture only', language: 'text', filepath: 'fixture.txt' },
        input: null,
        approval: null,
        bornAt: 0,
        phaseStartedAt: 0,
      }],
      focusId: 'visual-only-workspace',
      attention: null,
      panels: [],
    };
    const { default: SuperbrainReactiveEffects } = await import('./SuperbrainReactiveEffects');
    const view = render(<SuperbrainReactiveEffects tabSnapshotOverride={fixture} />);

    expect(view.container.querySelector('[data-testid="cortex-current"]')?.getAttribute('data-coordinates')).not.toBeNull();
    expect(view.container.querySelector('[data-testid="physical-conductor-path"]')).not.toBeNull();
    expect(getTabStoreSnapshot().tabs).toEqual([]);
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
