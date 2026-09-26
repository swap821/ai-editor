import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { act } from 'react';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import {
  __resetTabStoreForTests,
  focusMaterializedTab,
  getTabStoreSnapshot,
  showContentSurface,
} from '../superbrain/lib/tabStore';
import { setEmergencyStopPresentation } from '../livingMirror/emergencyStopPresentation';

// The 3D being is not testable in jsdom; stub it so we exercise the 2D chrome —
// specifically the DOM approval gate, the dependable supervised decision surface
// that does NOT depend on the WebGL scene rendering.
vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

// Keep the real adapter (real pending-approval store + __injectApproval), but stub
// the network-bound authorize/reject so the gate resolves without a backend.
// Mutable per-test return values so failure-path tests can flip the adapter's
// resolved outcome without re-mocking the whole module.
const approveResult: { ok: boolean; paused: boolean; answer: string } = {
  ok: true,
  paused: false,
  answer: '',
};
const rejectResult: { confirmed: boolean } = { confirmed: true };
const initialWrite = { paused: false };
let nextApproval: Record<string, unknown> | null = null;
const getLastEmittedCode = vi.fn(() => null);
const sendDirective = vi.fn(
  async (
    _text: string,
    _signal?: AbortSignal,
    _onChunk?: (answer: string) => void,
    onWritingCodeChunk?: (code: string, language?: string) => void,
  ) => {
    if (!initialWrite.paused) return { ok: true, paused: false, answer: '' };
    onWritingCodeChunk?.('print("partial")', 'python');
    const host = window as unknown as ApprovalHost;
    host.__injectApproval?.({
      token: 'first-write-token',
      summary: 'Approval required to create hello_loop.py',
      filepath: 'hello_loop.py',
      kind: 'create',
    });
    return { ok: true, paused: true, answer: '' };
  },
);

vi.mock('../superbrain/lib/intentRouting', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/intentRouting')>(
    '../superbrain/lib/intentRouting',
  );
  return { ...actual, isWorkIntent: () => true };
});

vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  return {
    ...actual,
    sendDirective,
    getLastEmittedCode,
    approvePendingApproval: vi.fn(async () => {
      const host = window as unknown as {
        __clearApproval?: () => void;
        __injectApproval?: (over?: Record<string, unknown>) => void;
      };
      host.__clearApproval?.();
      if (approveResult.paused) {
        host.__injectApproval?.(nextApproval ?? {
          summary: 'Approval required to run the next bounded step',
          kind: 'command',
          command: 'npm test',
        });
      }
      return { ...approveResult };
    }),
    rejectPendingApproval: vi.fn(async () => {
      (window as unknown as { __clearApproval?: () => void }).__clearApproval?.();
      return { ...rejectResult };
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
    __resetTabStoreForTests();
    setEmergencyStopPresentation('unknown');
    useMirrorStore.setState({
      recentEvents: [],
      lastEventId: null,
      lastTurnStartedEventId: null,
      lastVerificationEventId: null,
      approvalRequired: false,
      approvals: {},
      workers: {},
      verifications: {},
      lastVerification: null,
      phase: 'unknown',
      activeWorkers: [],
      activeMissions: [],
      activeCastes: [],
      activeModels: [],
      pendingEvents: 0,
    });
    approveResult.ok = true;
    approveResult.paused = false;
    approveResult.answer = '';
    initialWrite.paused = false;
    nextApproval = null;
    sendDirective.mockClear();
    getLastEmittedCode.mockReset().mockReturnValue(null);
    rejectResult.confirmed = true;
  });

  it('surfaces an actionable Allow once/Don\'t allow gate when the adapter has a pending approval', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    // No supervised pause yet -> no gate.
    expect(screen.queryByRole('alertdialog', { name: 'GAGOS permission request' })).toBeNull();

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
        screen.getByRole('alertdialog', { name: 'GAGOS permission request' }),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole('alertdialog', { name: 'GAGOS permission request' }),
    ).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('button', { name: /allow once/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /don.t allow/i })).toBeInTheDocument();
    // The decision names the exact action — never a vague ask (the target file
    // appears in both the title and the plain-language summary).
    expect(screen.getAllByText(/hello_loop\.py/i).length).toBeGreaterThan(0);

    // Keep the four human decision facts present in the integrated Guided DOM:
    // the user must be able to decide from what will happen, where it happens,
    // what the available evidence says it can affect, and what declining means.
    expect(screen.getByText('What', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('Where', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('It can affect', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('If you say no', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('GAGOS will not perform this action.')).toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: /allow once/i })).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /allow once/i }).click();
    });

    // The thread now carries a plain-language done-confirmation naming the action.
    await waitFor(() => {
      expect(screen.getAllByText(/hello_loop\.py/i).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/created|approved/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run a check' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Discard' })).toBeInTheDocument();

    await act(async () => {
      screen.getByRole('button', { name: 'Run a check' }).click();
    });
    expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toHaveValue('Run a check for hello_loop.py.');

    await act(async () => {
      screen.getByRole('button', { name: 'Discard' }).click();
    });
    expect(screen.getByText('Finished, but not verified')).toBeInTheDocument();
    expect(screen.getByText(/removed the unverified work surface/i)).toBeInTheDocument();
  });

  it('never narrates success when the authorize replay does not actually complete', async () => {
    approveResult.ok = false;
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
      expect(screen.getByRole('button', { name: /allow once/i })).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /allow once/i }).click();
    });

    // Must narrate the real failure, never a false "Created"/"Approved".
    await waitFor(() => {
      expect(screen.getByText(/failed to authorize/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/^↳ created/i)).toBeNull();
    expect(screen.queryByText(/^↳ approved/i)).toBeNull();
  });

  it('keeps a newly issued approval visible when an authorized replay pauses again', async () => {
    approveResult.ok = true;
    approveResult.paused = true;
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
      expect(screen.getByRole('button', { name: /allow once/i })).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /allow once/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByText(/run the next bounded step/i)).toBeInTheDocument();
    });
    expect(screen.queryByText('Finished, but not verified')).toBeNull();
    expect(screen.queryByText(/^↳ created/i)).toBeNull();
  });

  it('keeps final code and its unverified receipt on the same work tab across repeated approvals', async () => {
    initialWrite.paused = true;
    approveResult.paused = true;
    nextApproval = {
      token: 'second-write-token',
      summary: 'Approval required to finish hello_loop.py',
      filepath: 'hello_loop.py',
      kind: 'create',
      content: 'print("final")',
    };
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
    await act(async () => {
      fireEvent.change(input, { target: { value: 'create hello_loop.py' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByRole('alertdialog', { name: 'GAGOS permission request' })).toBeInTheDocument();
      expect(getTabStoreSnapshot().tabs.some(
        (tab) => tab.kind === 'content' && tab.content?.code === 'print("partial")',
      )).toBe(true);
    });
    const originalTab = getTabStoreSnapshot().tabs.find(
      (tab) => tab.kind === 'content' && tab.content?.filepath === 'hello_loop.py',
    );
    expect(originalTab).toBeDefined();
    const originalTabId = originalTab!.id;

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /allow once/i }));
    });
    await waitFor(() => {
      expect(screen.getByText(/finish hello_loop\.py/i)).toBeInTheDocument();
    });

    approveResult.paused = false;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /allow once/i }));
    });

    await waitFor(() => {
      const finalTab = getTabStoreSnapshot().tabs.find((tab) => tab.id === originalTabId);
      expect(finalTab?.content?.code).toBe('print("final")');
      expect(finalTab?.content?.streaming).toBe(false);
    });
    expect(getTabStoreSnapshot().tabs.filter(
      (tab) => tab.kind === 'content' && tab.content?.filepath === 'hello_loop.py',
    ).map((tab) => tab.id)).toEqual([originalTabId]);
    expect(screen.getByText('Finished, but not verified')).toBeInTheDocument();
    expect(getTabStoreSnapshot().tabs.find((tab) => tab.id === originalTabId)?.content?.verifyVerdict)
      .toBeUndefined();

    const otherTab = showContentSurface({
      code: 'print("other")',
      language: 'python',
      filepath: 'other.py',
      streaming: false,
    });
    focusMaterializedTab(otherTab.id);
    expect(getTabStoreSnapshot().focusId).toBe(otherTab.id);

    const receipt = screen.getByRole('status', { name: 'Finished, but not verified' });
    await act(async () => {
      fireEvent.click(within(receipt).getByRole('button', { name: 'Review' }));
    });
    expect(getTabStoreSnapshot().focusId).toBe(originalTabId);
  });

  it('narrates an unconfirmed decline distinctly from a confirmed one', async () => {
    rejectResult.confirmed = false;
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
      expect(screen.getByRole('button', { name: /don.t allow/i })).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /don.t allow/i }).click();
    });

    await waitFor(() => {
      expect(screen.getByText(/unconfirmed by the server/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/decline was not confirmed by the server/i)).toBeInTheDocument();
    expect(screen.getByText(/this interface did not authorize the action/i)).toBeInTheDocument();
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
        screen.getByRole('alertdialog', { name: 'GAGOS permission request' }),
      ).toBeInTheDocument();
    });

    act(() => {
      (window as unknown as ApprovalHost).__clearApproval?.();
    });
    await waitFor(() => {
      expect(
        screen.queryByRole('alertdialog', { name: 'GAGOS permission request' }),
      ).toBeNull();
    });
  });

  it('holds approval action presentation while an admitted emergency stop is engaged', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      (window as unknown as ApprovalHost).__injectApproval?.({
        summary: 'Approval required to create hello_loop.py',
        filepath: 'hello_loop.py',
        kind: 'create',
      });
      useMirrorStore.getState().applyEvent(1, 'governance.emergency_stop.engaged', { reason: 'operator stop' });
    });

    await waitFor(() => {
      expect(screen.getByText(/permission request is being held/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('alertdialog', { name: 'GAGOS permission request' })).toBeNull();
    expect(screen.queryByRole('button', { name: /allow once/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /don.t allow/i })).toBeNull();
  });

  it('holds approval presentation from a confirmed stop latch even before a mirror event arrives', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    act(() => {
      setEmergencyStopPresentation('engaged');
      (window as unknown as ApprovalHost).__injectApproval?.({
        summary: 'Approval required to create hello_loop.py',
        filepath: 'hello_loop.py',
        kind: 'create',
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/permission request is being held/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('alertdialog', { name: 'GAGOS permission request' })).toBeNull();
    expect(screen.queryByRole('button', { name: /allow once/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /don.t allow/i })).toBeNull();
  });
});
