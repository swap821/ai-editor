import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';

// The 3D canvas is not testable in jsdom; stub the being so we can exercise the
// 2D chrome layer (verify toast, approval surface, etc.).
vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

describe('GagosChrome verify toast', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
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
