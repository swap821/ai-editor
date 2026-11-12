import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import WorkspaceCanvas from './WorkspaceCanvas';

const mocks = vi.hoisted(() => ({
  notifyDirective: vi.fn(),
  tickLifecycle: vi.fn(),
  startAiosPolling: vi.fn(),
  stopPolling: vi.fn(),
  subscribeCognition: vi.fn(),
  unsubscribe: vi.fn(),
  useQualityTier: vi.fn(),
  useFeatureGate: vi.fn(),
}));

vi.mock('@/lib/cognitionBus', () => ({ subscribeCognition: mocks.subscribeCognition }));
vi.mock('@/lib/constants', () => ({
  POST_FX: { toneMappingExposure: 1 },
  CAMERA: { fov: 50, near: 0.1, far: 500 },
}));
vi.mock('@/components/QualityTierProvider', () => ({
  QualityTierBoundary: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useQualityTier: mocks.useQualityTier,
}));
vi.mock('@/lib/perfBudget', () => ({ TIER_DPR: { low: 0.75, high: 1.25 } }));
vi.mock('@/lib/aiosAdapter', () => ({ startAiosPolling: mocks.startAiosPolling }));
vi.mock('@/lib/lifecycleStateMachine', () => ({
  notifyDirective: mocks.notifyDirective,
  tickLifecycle: mocks.tickLifecycle,
}));
vi.mock('../../core/Performance/FeatureGate', () => ({ useFeatureGate: mocks.useFeatureGate }));
vi.mock('../../core/CortexEngine', () => ({
  default: (props: { mode: string; activity: number; sky: string; surface: string }) => (
    <div
      data-testid="cortex"
      data-mode={props.mode}
      data-activity={String(props.activity)}
      data-sky={props.sky}
      data-surface={props.surface}
    />
  ),
}));
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children, dpr }: { children?: React.ReactNode; dpr?: number }) => (
    <div data-testid="canvas" data-dpr={String(dpr)}>
      {children}
    </div>
  ),
  useFrame: vi.fn(),
}));
vi.mock('./TierGovernor', () => ({ default: () => null }));
vi.mock('./RenderFrameLoop', () => ({
  default: ({ sleeping }: { sleeping: boolean }) => (
    <div data-testid="frame-loop" data-sleeping={String(sleeping)} />
  ),
}));
vi.mock('./WebGLErrorBoundary', () => ({
  WebGLErrorBoundary: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  WebGLFallback: ({ onRetry }: { onRetry?: () => void }) => (
    <div data-testid="fallback">{onRetry ? <button onClick={onRetry}>Retry</button> : null}</div>
  ),
}));

function stubWebGL(available: boolean) {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() =>
    available ? ({} as unknown as RenderingContext) : null,
  );
}

describe('WorkspaceCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    mocks.useQualityTier.mockReturnValue({
      tier: 'high',
      perfTier: 'low',
      preference: 'manual',
      autoProfile: { dpr: 1.5 },
    });
    mocks.useFeatureGate.mockReturnValue(true);
    mocks.subscribeCognition.mockReturnValue(mocks.unsubscribe);
    mocks.startAiosPolling.mockReturnValue(mocks.stopPolling);
    stubWebGL(true);
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders the accessible fallback instead of the canvas without WebGL', () => {
    stubWebGL(false);
    const { container } = render(<WorkspaceCanvas booted>{<span>child</span>}</WorkspaceCanvas>);
    expect(screen.getByTestId('fallback')).toBeInTheDocument();
    expect(screen.queryByTestId('canvas')).toBeNull();
    expect(screen.queryByText('child')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
    expect(container.firstElementChild).toHaveClass('is-booted');
  });

  it('mounts the canvas with children, manual-tier dpr and the default look', () => {
    const { container } = render(
      <WorkspaceCanvas>
        <span>child</span>
      </WorkspaceCanvas>,
    );
    const canvas = screen.getByTestId('canvas');
    expect(canvas).toHaveAttribute('data-dpr', '0.75');
    expect(canvas).toContainElement(screen.getByText('child'));
    expect(screen.getByTestId('frame-loop')).toHaveAttribute('data-sleeping', 'true');
    const cortex = screen.getByTestId('cortex');
    expect(cortex).toHaveAttribute('data-mode', 'orchestrate');
    expect(cortex).toHaveAttribute('data-activity', '0.72');
    expect(cortex).toHaveAttribute('data-sky', 'voyage');
    expect(cortex).toHaveAttribute('data-surface', 'web');
    expect(container.firstElementChild).toHaveClass('is-booting');
  });

  it('uses the auto profile dpr when the preference is auto', () => {
    mocks.useQualityTier.mockReturnValue({
      tier: 'high',
      perfTier: 'low',
      preference: 'auto',
      autoProfile: { dpr: 1.5 },
    });
    render(<WorkspaceCanvas />);
    expect(screen.getByTestId('canvas')).toHaveAttribute('data-dpr', '1.5');
  });

  it('honours stored sky and surface choices and ignores invalid ones', () => {
    window.localStorage.setItem('gag-sky-mode-v1', 'layered');
    window.localStorage.setItem('gag-brain-surface-v1', 'organ');
    render(<WorkspaceCanvas />);
    expect(screen.getByTestId('cortex')).toHaveAttribute('data-sky', 'layered');
    expect(screen.getByTestId('cortex')).toHaveAttribute('data-surface', 'organ');
    cleanup();

    window.localStorage.setItem('gag-sky-mode-v1', 'bogus');
    window.localStorage.setItem('gag-brain-surface-v1', 'bogus');
    render(<WorkspaceCanvas />);
    expect(screen.getByTestId('cortex')).toHaveAttribute('data-sky', 'voyage');
    expect(screen.getByTestId('cortex')).toHaveAttribute('data-surface', 'web');
  });

  it('starts AIOS polling only once booted and stops it on unmount', () => {
    const { rerender, unmount } = render(<WorkspaceCanvas booted={false} />);
    expect(mocks.startAiosPolling).not.toHaveBeenCalled();
    rerender(<WorkspaceCanvas booted />);
    expect(mocks.startAiosPolling).toHaveBeenCalledTimes(1);
    expect(mocks.stopPolling).not.toHaveBeenCalled();
    unmount();
    expect(mocks.stopPolling).toHaveBeenCalledTimes(1);
  });

  it('wakes the being on directives and ticks the lifecycle every 50ms until unmount', () => {
    vi.useFakeTimers();
    const { unmount } = render(<WorkspaceCanvas />);
    const listener = mocks.subscribeCognition.mock.calls[0][0] as (event: { type: string }) => void;

    listener({ type: 'other' });
    expect(mocks.notifyDirective).not.toHaveBeenCalled();
    listener({ type: 'directive' });
    expect(mocks.notifyDirective).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(mocks.tickLifecycle).toHaveBeenCalledTimes(3);

    unmount();
    expect(mocks.unsubscribe).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(mocks.tickLifecycle).toHaveBeenCalledTimes(3);
  });
});
