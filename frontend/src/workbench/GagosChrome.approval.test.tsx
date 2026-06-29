import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';

// The 3D being is not testable in jsdom; stub it so we exercise the 2D chrome —
// specifically the DOM approval gate, the dependable supervised decision surface
// that does NOT depend on the WebGL scene rendering.
vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

// Keep the real adapter (real pending-approval store + __injectApproval), but stub
// the network-bound authorize/reject so the gate resolves without a backend.
vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  return {
    ...actual,
    approvePendingApproval: vi.fn(async () => {
      (window as unknown as { __clearApproval?: () => void }).__clearApproval?.();
      return { ok: true, paused: false, answer: '' };
    }),
    rejectPendingApproval: vi.fn(async () => {
      (window as unknown as { __clearApproval?: () => void }).__clearApproval?.();
    }),
  };
});

type ApprovalHost = {
  __injectApproval?: (over?: Record<string, unknown>) => void;
  __clearApproval?: () => void;
};

describe('GagosChrome DOM approval gate', () => {
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
    (window as unknown as ApprovalHost).__clearApproval?.();
  });

  it('surfaces an actionable AUTHORIZE/REJECT gate when the adapter has a pending approval', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    // No supervised pause yet -> no gate.
    expect(screen.queryByRole('alertdialog', { name: /operator approval required/i })).toBeNull();

    // The backend pauses on a real write intent -> the adapter captures the
    // pending approval (this is exactly what a live YELLOW turn produces).
    act(() => {
      (window as unknown as ApprovalHost).__injectApproval?.({
        summary: 'Approval required to create hello_loop.py',
        filepath: 'hello_loop.py',
        kind: 'create',
      });
    });

    // The operator now has a real, clickable decision surface IN THE CHROME,
    // independent of whether the 3D scene renders.
    await waitFor(() => {
      expect(
        screen.getByRole('alertdialog', { name: /operator approval required/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /authorize/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
    // The decision names the exact action — never a vague ask (the target file
    // appears in both the title and the plain-language summary).
    expect(screen.getAllByText(/hello_loop\.py/i).length).toBeGreaterThan(0);
  });

  it('pushes a DOM confirmation into the thread after the operator authorizes', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      (window as unknown as ApprovalHost & { __injectApproval?: (o?: Record<string, unknown>) => void }).__injectApproval?.({
        summary: 'Approval required to create hello_loop.py',
        filepath: 'hello_loop.py',
        kind: 'create',
      });
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /authorize/i })).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /authorize/i }).click();
    });

    // The thread now carries a plain-language done-confirmation naming the action.
    await waitFor(() => {
      expect(screen.getByText(/hello_loop\.py/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/created|approved/i)).toBeInTheDocument();
  });

  it('clears the gate once the pending approval is resolved', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      (window as unknown as ApprovalHost).__injectApproval?.({
        summary: 'Approval required to create hello_loop.py',
        filepath: 'hello_loop.py',
        kind: 'create',
      });
    });
    await waitFor(() => {
      expect(
        screen.getByRole('alertdialog', { name: /operator approval required/i }),
      ).toBeInTheDocument();
    });

    act(() => {
      (window as unknown as ApprovalHost).__clearApproval?.();
    });
    await waitFor(() => {
      expect(
        screen.queryByRole('alertdialog', { name: /operator approval required/i }),
      ).toBeNull();
    });
  });
});
