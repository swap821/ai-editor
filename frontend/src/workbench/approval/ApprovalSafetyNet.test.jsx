import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

// ── Mocks ──────────────────────────────────────────────────────────────────────
// The adapter is a port-managed TS module; mock only the exported approval surface
// the safety-net consumes, so the test never touches the network or the real poller.
// `mockPending` is the single source the guard reconciles to (getPendingApproval()).
let mockPending = null;
const approveMock = vi.fn();
const rejectMock = vi.fn();

const busListeners = new Set();
function publishToBus(event) {
  for (const l of busListeners) l(event);
}

vi.mock('../../superbrain/lib/aiosAdapter', () => ({
  getPendingApproval: () => mockPending,
  approvePendingApproval: (...args) => {
    // Mirror the real adapter: clears the persisted token SYNCHRONOUSLY at entry
    // (before any await), so the guard's optimistic sync() observes null at once.
    mockPending = null;
    approveMock(...args);
    return Promise.resolve({ ok: true, paused: false, answer: '' });
  },
  rejectPendingApproval: (...args) => {
    mockPending = null;
    rejectMock(...args);
    return Promise.resolve();
  },
}));
vi.mock('../../superbrain/lib/cognitionBus', () => ({
  subscribeCognition: (listener) => {
    busListeners.add(listener);
    return () => busListeners.delete(listener);
  },
  publishCognition: (e) => publishToBus(e),
}));

import ApprovalSafetyNet from './ApprovalSafetyNet';

const PENDING_EDIT = {
  token: 'tok-1',
  prompt: 'edit the config',
  summary: 'Edit aios/config.py to flip the flag',
  explanation: 'A YELLOW edit awaiting operator authorization.',
  diff: '--- a/config.py\n+++ b/config.py\n@@ -1 +1 @@\n-FLAG = False\n+FLAG = True',
  command: '',
  kind: 'edit',
  filepath: 'aios/config.py',
  content: '',
};

const PENDING_CMD = {
  token: 'tok-2',
  prompt: 'run pytest',
  summary: 'Run the test suite',
  explanation: '',
  diff: '',
  command: 'pytest -q',
  kind: 'command',
  filepath: '',
  content: '',
};

beforeEach(() => {
  mockPending = null;
  busListeners.clear();
  approveMock.mockClear();
  rejectMock.mockClear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('ApprovalSafetyNet', () => {
  it('1. RELIABILITY: a persisted token with NO approval-required bus event ever fired still surfaces AUTHORIZE/REJECT after poll + grace', () => {
    vi.useFakeTimers();
    // Token persists at mount, but no bus event will EVER be published — the exact
    // defect (HUD-local state never set). Only the poll + grace can save it.
    mockPending = PENDING_EDIT;
    render(<ApprovalSafetyNet />);

    // Inside the grace window: nothing renders yet (no double UI with the canon panel).
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    // Advance past the poll (1200ms) AND the grace (1500ms): the guard reconciles
    // from the persisted adapter truth alone and paints the actionable surface.
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole('alertdialog', { name: /resolve pending approval/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /authorize/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
    // Distinct identity: the role-explaining eyebrow + the diff content.
    expect(screen.getByText(/recovered from a missed approval signal/i)).toBeInTheDocument();
    expect(screen.getByText(/Edit aios\/config\.py to flip the flag/i)).toBeInTheDocument();
  });

  it('2. NO DOUBLE UI: within the grace window the guard renders nothing', () => {
    vi.useFakeTimers();
    mockPending = PENDING_EDIT;
    render(<ApprovalSafetyNet />);
    // A poll fires but the grace has not elapsed → still nothing (canon panel owns
    // this window in the healthy path).
    act(() => {
      vi.advanceTimersByTime(1300); // > 1 poll, < grace
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('3. INSTANT CLEAR: AUTHORIZE calls the adapter once and the surface clears optimistically (synchronously)', () => {
    vi.useFakeTimers();
    mockPending = PENDING_CMD;
    render(<ApprovalSafetyNet />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    const authorize = screen.getByRole('button', { name: /authorize/i });
    expect(authorize).toBeInTheDocument();

    // Click → optimistic clear: the adapter nulls the token synchronously at entry
    // and the guard sync()s immediately, so the surface vanishes without awaiting
    // the network round-trip.
    act(() => {
      fireEvent.click(authorize);
    });
    expect(approveMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('3b. INSTANT CLEAR: REJECT calls rejectPendingApproval once and clears optimistically', () => {
    vi.useFakeTimers();
    mockPending = PENDING_CMD;
    render(<ApprovalSafetyNet />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /reject/i }));
    });
    expect(rejectMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('4. RE-ARM: after resolve, a NEW token restarts the grace and the guard re-shows', () => {
    vi.useFakeTimers();
    mockPending = PENDING_EDIT;
    render(<ApprovalSafetyNet />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();

    // Resolve via AUTHORIZE (replay) → surface clears.
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /authorize/i }));
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    // The replay paused AGAIN on the next caution action and re-captured a FRESH,
    // DIFFERENT token. The grace timer must restart cleanly (token-change keyed).
    mockPending = PENDING_CMD; // different token (tok-2)
    // Within the new grace window: still hidden.
    act(() => {
      vi.advanceTimersByTime(1300);
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    // Past the new grace: re-armed and visible again.
    act(() => {
      vi.advanceTimersByTime(800);
    });
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/Run the test suite/i)).toBeInTheDocument();
  });

  it('5. Z-INDEX: the portal wrapper carries the documented class pinned to z 62 (jsdom does not load CSS — assert the class, per the OrgansDock convention)', () => {
    vi.useFakeTimers();
    mockPending = PENDING_EDIT;
    render(<ApprovalSafetyNet />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    // The portal mounts into document.body; the wrapper carries .approval-guard whose
    // approval-safety-net.css comment pins z-index:62 (the new ceiling above the canon
    // band z 60 and organs z 55). Geometry is enforced by the CSS + check_css_canon;
    // here we assert the wrapper class the CSS targets exists.
    const wrapper = document.body.querySelector('.approval-guard');
    expect(wrapper).toBeTruthy();
    expect(wrapper.getAttribute('data-z')).toBe('62');
    expect(wrapper.querySelector('.approval-guard-card')).toBeTruthy();
  });

  it('6. resolve to null hides the guard (poll-driven)', () => {
    vi.useFakeTimers();
    mockPending = PENDING_EDIT;
    render(<ApprovalSafetyNet />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    // The token is redeemed elsewhere (e.g. the canon panel finally mounted and the
    // operator acted there) → getPendingApproval() goes null; the poll reconciles.
    mockPending = null;
    act(() => {
      vi.advanceTimersByTime(1300);
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});
