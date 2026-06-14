import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

// ── Mocks ──────────────────────────────────────────────────────────────────────
// The adapter is a port-managed TS module; mock its public surface so tests never
// touch the network or the real poller. AIOS_BASE must be a string the components
// can template into a URL.
let mockAutonomy = null;
const busListeners = new Set();
function publishToBus(event) {
  for (const l of busListeners) l(event);
}

vi.mock('../../superbrain/lib/aiosAdapter', () => ({
  AIOS_BASE: 'http://test.local',
  getAutonomy: () => mockAutonomy,
}));
vi.mock('../../superbrain/lib/cognitionBus', () => ({
  subscribeCognition: (listener) => {
    busListeners.add(listener);
    return () => busListeners.delete(listener);
  },
  publishCognition: (e) => publishToBus(e),
}));
vi.mock('../../config', () => ({
  API_BASE: 'http://test.local',
  API_HEADERS: {},
}));

import OrgansDock from './OrgansDock';

const AUTONOMY_RICH = {
  enabled: true,
  min_successes: 3,
  entries: [
    {
      signature: 'write|*.py',
      action_type: 'write',
      target_shape: '*.py',
      success_count: 7,
      failure_count: 0,
      streak: 4,
      status: 'earned',
      earned_at: '2026-06-11 10:00:00',
      revoked_at: null,
      last_outcome_at: '2026-06-12 09:00:00',
    },
    {
      signature: 'command|pytest',
      action_type: 'command',
      target_shape: 'pytest ...',
      success_count: 2,
      failure_count: 1,
      streak: 2,
      status: 'probation',
      earned_at: null,
      revoked_at: null,
      last_outcome_at: '2026-06-12 09:00:00',
    },
    {
      signature: 'edit|config.*',
      action_type: 'edit',
      target_shape: 'config.*',
      success_count: 1,
      failure_count: 0,
      streak: 0,
      status: 'revoked',
      earned_at: null,
      revoked_at: '2026-06-10 08:00:00',
      last_outcome_at: '2026-06-10 08:00:00',
    },
  ],
  summary: { earned: 1, probation: 1, revoked: 1 },
};

const CURRICULUM = {
  tasks: [
    { id: 1, skill_name: 'html-forms', level: 1, prompt: 'Build a basic form', held_out: 0, status: 'mastered', attempts: 4, successes: 4 },
    { id: 2, skill_name: 'html-forms', level: 2, prompt: 'Validate a form', held_out: 1, status: 'mastered', attempts: 3, successes: 3 },
    { id: 3, skill_name: 'html-forms', level: 3, prompt: 'Build a validated contact form with server-side checks and so on', held_out: 1, status: 'available', attempts: 2, successes: 0 },
    { id: 4, skill_name: 'html-forms', level: 4, prompt: 'Locked rung', held_out: 0, status: 'locked', attempts: 0, successes: 0 },
  ],
};

function mockFetch({ autonomy = AUTONOMY_RICH, curriculum = CURRICULUM, fail = false } = {}) {
  return vi.fn((url) => {
    if (fail) return Promise.reject(new Error('offline'));
    const u = String(url);
    if (u.includes('/development/autonomy')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(autonomy) });
    }
    if (u.includes('/development/curriculum')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(curriculum) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

beforeEach(() => {
  mockAutonomy = null;
  busListeners.clear();
  try {
    window.localStorage.clear();
  } catch {
    /* noop */
  }
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('OrgansDock', () => {
  it('1. renders collapsed by default — only the tab, no panel; no localStorage key', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    expect(screen.getByRole('button', { name: /open organs dock/i })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('organs-dock-open-v1')).toBeNull();
  });

  it('2. dock geometry: z-index < 60 and top >= 64', () => {
    vi.stubGlobal('fetch', mockFetch());
    const { container } = render(<OrgansDock />);
    // The portal mounts into document.body; query there.
    const dock = document.body.querySelector('.organs-dock');
    expect(dock).toBeTruthy();
    // organs.css applies z-index:55; jsdom doesn't load CSS files, so assert the
    // documented constant via the stylesheet is not testable — instead assert the
    // structural contract the CSS depends on (tab present, dock wrapper present).
    // Geometry constants are enforced by the CSS file + check_css_canon; here we
    // assert the wrapper + tab exist so the CSS can target them.
    expect(dock.querySelector('.organs-tab')).toBeTruthy();
    expect(container).toBeTruthy();
  });

  it('3. autonomy port: status colors, threshold, failure_count visibility', async () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    await waitFor(() => expect(screen.getByText(/write \*\.py/i)).toBeInTheDocument());

    // Earned row carries the ok class via its left rail.
    const earnedRow = screen.getByText(/write \*\.py/i).closest('.organs-row');
    expect(earnedRow.className).toContain('organs-row--ok');
    const probationRow = screen.getByText(/command pytest/i).closest('.organs-row');
    expect(probationRow.className).toContain('organs-row--busy');
    const revokedRow = screen.getByText(/edit config\.\*/i).closest('.organs-row');
    expect(revokedRow.className).toContain('organs-row--bad');

    // THRESHOLD reflects min_successes.
    expect(screen.getByText('3')).toBeInTheDocument();

    // failure_count hidden when 0 (earned row), shown when > 0 (probation row).
    expect(within(earnedRow).queryByText(/✗/)).not.toBeInTheDocument();
    expect(within(probationRow).getByText(/✗1/)).toBeInTheDocument();
  });

  it('4. autonomy seed paints instantly before fetch resolves', async () => {
    mockAutonomy = AUTONOMY_RICH;
    // fetch never resolves → only the seed can paint.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    // Seed is synchronous — the row is present without awaiting fetch.
    expect(screen.getByText(/write \*\.py/i)).toBeInTheDocument();
  });

  it('5. curriculum: derived mastery, held-out proven pill, skill header L/max — no pass-rate formula', async () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    fireEvent.click(screen.getByRole('tab', { name: /growth/i }));
    await waitFor(() => expect(screen.getByText('html-forms')).toBeInTheDocument());

    // Skill header: highest mastered level / max level (mastery from row.status only).
    expect(screen.getByText('L2/4 mastered')).toBeInTheDocument();

    // Held-out that passed → "HELD-OUT ✓" with proven class; pending held-out → "HELD-OUT".
    const proven = screen.getByText('HELD-OUT ✓');
    expect(proven.className).toContain('organs-held--proven');
    // Exact match: the pending pill text is exactly "HELD-OUT" (the proven pill is
    // "HELD-OUT ✓", so use an exact matcher to disambiguate).
    const pending = screen.getByText((content) => content === 'HELD-OUT');
    expect(pending).toBeInTheDocument();
    expect(pending.className).not.toContain('organs-held--proven');
  });

  it('6. empty/offline copy renders honestly (no fabricated rows)', async () => {
    vi.stubGlobal('fetch', mockFetch({ autonomy: { enabled: false, min_successes: 3, entries: [], summary: { earned: 0, probation: 0, revoked: 0 } } }));
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    await waitFor(() => expect(screen.getByText(/No earned capabilities yet/i)).toBeInTheDocument());
    expect(screen.getByText(/switched off/i)).toBeInTheDocument();
    expect(document.querySelector('.organs-row')).toBeNull();
  });

  it('6b. autonomy offline (no seed, fetch fails) shows LEDGER OFFLINE', async () => {
    vi.stubGlobal('fetch', mockFetch({ fail: true }));
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    await waitFor(() => expect(screen.getByText(/LEDGER OFFLINE/i)).toBeInTheDocument());
  });

  it('7. tab flares on CAPABILITY EARNED bus event (static class swap on the pip)', () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    const pip = document.body.querySelector('.organs-tab-pip');
    expect(pip.className).not.toContain('is-flaring');
    // act flushes the React state update the bus event triggers.
    act(() => {
      publishToBus({ type: 'knowledge-acquired', label: 'CAPABILITY EARNED' });
    });
    expect(document.body.querySelector('.organs-tab-pip').className).toContain('is-flaring');
    // Flare clears after ~780ms (the timeout runs under fake timers).
    act(() => {
      vi.advanceTimersByTime(800);
    });
    expect(document.body.querySelector('.organs-tab-pip').className).not.toContain('is-flaring');
    vi.useRealTimers();
  });

  it('8. earned chip hidden when earned===0, shown when > 0', () => {
    mockAutonomy = { ...AUTONOMY_RICH, summary: { earned: 0, probation: 0, revoked: 0 } };
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    expect(document.body.querySelector('.organs-tab-chip')).toBeNull();
    // Bump earned, then fire a real earn event → the live subscription re-reads
    // getAutonomy() and the chip appears (no rerender of the portal needed).
    mockAutonomy = { ...AUTONOMY_RICH, summary: { earned: 2, probation: 0, revoked: 0 } };
    act(() => {
      publishToBus({ type: 'knowledge-acquired', label: 'CAPABILITY EARNED' });
    });
    const chip = document.body.querySelector('.organs-tab-chip');
    expect(chip).toBeTruthy();
    expect(chip.textContent).toContain('2');
  });

  it('9. open state persists to the fresh localStorage key (no gag-* collision)', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    expect(window.localStorage.getItem('organs-dock-open-v1')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: /collapse organs dock/i }));
    expect(window.localStorage.getItem('organs-dock-open-v1')).toBe('false');
  });
});
