import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import { __resetTabStoreForTests, beginRetractingMaterializedTab, finishMaterializedTabRetraction, getTabStoreSnapshot, showContentSurface } from '../superbrain/lib/tabStore';

beforeEach(() => __resetTabStoreForTests());
afterEach(() => { cleanup(); __resetTabStoreForTests(); });
function matchingArtifact(filepath = 'test_demo_module.py') {
  return showContentSurface({ filepath, code: 'print("example")', language: 'python', streaming: false });
}

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

  it('renders a transient verify PASS toast for a uniquely matched artifact', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    matchingArtifact();
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

  it.each(['missing', 'same-path', 'targetless', 'inconclusive'])('does not celebrate an unbound %s check', async (scenario) => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const first = matchingArtifact();
    if (scenario === 'same-path') {
      beginRetractingMaterializedTab(first.id);
      finishMaterializedTabRetraction(first.id, getTabStoreSnapshot().tabs.find((tab) => tab.id === first.id)?.retractionToken);
      matchingArtifact();
      expect(getTabStoreSnapshot().recoverableTabs?.[0].id).toBe(first.id);
    } else if (scenario === 'targetless') matchingArtifact('other.py');
    render(<GagosChrome />);
    act(() => publishCognition({ type: 'verify', source: 'mirror', metadata: { mirrorEventId: 7 },
      data: { verdict: scenario === 'inconclusive' ? 'unavailable' : 'pass',
        target: scenario === 'targetless' ? '' : scenario === 'missing' ? 'missing.py' : 'test_demo_module.py' },
    }));
    const toast = await screen.findByText('Check not attributed');
    expect(toast).toHaveClass('gagos-verify-toast--unknown');
    expect(toast).not.toHaveClass('gagos-verify-toast--pass', 'gagos-verify-toast--fail');
    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
    expect(getTabStoreSnapshot().tabs.find((tab) => tab.id === first.id)?.content?.verifyVerdict).toBeUndefined();
    expect(getTabStoreSnapshot().tabs.find((tab) => tab.id === first.id)?.content?.verifyEventId).toBeUndefined();
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
    matchingArtifact();
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
    matchingArtifact();
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
