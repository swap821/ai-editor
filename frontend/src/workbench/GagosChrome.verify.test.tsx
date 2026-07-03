import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';

// The 3D canvas is not testable in jsdom; stub the being so we can exercise the
// 2D chrome layer (verify toast, approval surface, etc.).
vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

function mockMatchMedia(reducedMotion: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: reducedMotion && query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('GagosChrome verify toast', () => {
  beforeEach(() => {
    mockMatchMedia(false);
  });

  it('renders a transient verify PASS toast when the cognition bus fires a verify event', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      publishCognition({
        type: 'verify',
        label: 'VERIFY PASS',
        detail: 'test_demo_module.py',
        intensity: 0.75,
        source: 'aios',
        data: { verdict: 'pass', target: 'test_demo_module.py' },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Verified')).toHaveClass('gagos-verify-toast');
    });
  });
});

describe('GagosChrome verify toast authored exit (W4.1)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockMatchMedia(false);
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('enters a leaving sub-state ~250ms before unmount, mirrored exit class applied', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      publishCognition({
        type: 'verify',
        label: 'VERIFY PASS',
        detail: 'test_demo_module.py',
        intensity: 0.75,
        source: 'aios',
        data: { verdict: 'pass', target: 'test_demo_module.py' },
      });
    });

    // Toast is up and NOT yet leaving.
    expect(screen.getByText('Verified')).not.toHaveClass('gagos-verify-toast--leaving');

    // After the 2600ms hold, it enters the leaving sub-state (still mounted).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2600);
    });
    expect(screen.getByText('Verified')).toHaveClass('gagos-verify-toast--leaving');

    // ~250ms later it unmounts entirely.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  });
});

describe('GagosChrome verify toast reduced-motion (W4.1)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockMatchMedia(true);
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('skips the leaving delay and unmounts immediately when reduced-motion is on', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      publishCognition({
        type: 'verify',
        label: 'VERIFY PASS',
        detail: 'test_demo_module.py',
        intensity: 0.75,
        source: 'aios',
        data: { verdict: 'pass', target: 'test_demo_module.py' },
      });
    });

    expect(screen.getByText('Verified')).toBeInTheDocument();

    // At the 2600ms hold mark, reduced-motion unmounts directly — no
    // intermediate 'leaving' class, no extra 250ms wait required.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2600);
    });
    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  });
});
