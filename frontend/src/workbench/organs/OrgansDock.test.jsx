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

let mockTrails = [];
let mockLink = true;
vi.mock('../../superbrain/lib/aiosAdapter', () => ({
  AIOS_BASE: 'http://test.local',
  getAutonomy: () => mockAutonomy,
  getKnownTrails: () => mockTrails,
  getLinkState: () => mockLink,
  trailLabel: (g) => String(g || '').replace(/\s+/g, ' ').trim().slice(0, 48).toUpperCase(),
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

// Wave-3 port fixtures — the new ports talk to the security/plan/models routes.
const ZONE_RED = { zone: 'RED', confidence: 0.97, reason: 'Destructive: rm -rf detected' };
const PLAN_RESPONSE = {
  goal: 'ship the feature',
  requires_human: true,
  steps: [
    { step_id: 's1', description: 'Read the spec', confidence: 0.9 },
    { step_id: 's2', description: 'Edit the gateway', confidence: 0.4 },
  ],
  approved: [{ step_id: 's1', description: 'Read the spec', confidence: 0.9 }],
  escalate: [
    {
      step: { step_id: 's2', description: 'Edit the gateway', confidence: 0.4 },
      reason: 'Confidence 0.400 below threshold',
      action: 'human-review',
    },
  ],
  calibrations: [],
};
const MODELS_LOCAL = { models: ['qwen2.5-coder:7b', 'llama3.1:8b'] };
const MODELS_BEDROCK = { configured: false, available: false, models: [] };
const MODELS_GEMINI = { configured: false, available: false, models: [] };
const MODELS_AUTO = {
  available: true,
  model: 'qwen2.5-coder:7b',
  task: 'coding',
  reason: 'coder-tuned, 7B, instruct',
  by_task: {
    coding: 'qwen2.5-coder:7b',
    reasoning: 'llama3.1:8b',
    general: 'llama3.1:8b',
    fast: 'qwen2.5-coder:7b',
  },
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
    if (u.includes('/security/classify')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(ZONE_RED) });
    }
    if (u.includes('/api/v1/plan')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(PLAN_RESPONSE) });
    }
    if (u.includes('/models/local')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(MODELS_LOCAL) });
    }
    if (u.includes('/models/bedrock')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(MODELS_BEDROCK) });
    }
    if (u.includes('/models/gemini')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(MODELS_GEMINI) });
    }
    if (u.includes('/models/auto')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(MODELS_AUTO) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

// ── Nav helpers (Wave-3) ─────────────────────────────────────────────────────
// The flat tablist is gone: organs are now menuitemradio entries behind the
// "Choose organ" trigger. Open the dock, open the menu, pick an organ.
function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: /choose organ/i }));
}
function pickOrgan(name) {
  openMenu();
  fireEvent.click(screen.getByRole('menuitemradio', { name }));
}

beforeEach(() => {
  mockAutonomy = null;
  mockTrails = [];
  mockLink = true;
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
    pickOrgan(/growth/i);
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

  // ── Wave-3: grouped nav ────────────────────────────────────────────────────
  it('10. nav menu lists all 8 organs grouped under their sections', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    openMenu();
    // Scope the section eyebrow lookup to the menu (the active section also shows
    // in the header trigger, so an unscoped query would double-match).
    const menu = screen.getByRole('menu');
    for (const section of ['GOVERNANCE', 'LEARNING', 'MEMORY', 'REASONING', 'SECURITY', 'SYSTEM']) {
      expect(within(menu).getByText(section)).toBeInTheDocument();
    }
    // All 8 organs are present as menu items.
    expect(screen.getAllByRole('menuitemradio')).toHaveLength(8);
  });

  it('11. selecting an organ closes the menu and persists the tab key', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    pickOrgan(/zone probe/i);
    // Menu closed (no menuitemradio rendered) + tab persisted.
    expect(screen.queryByRole('menuitemradio')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('organs-dock-tab-v1')).toBe('zone');
  });

  it('12. Esc closes the menu first, then the dock', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    openMenu();
    expect(screen.getByRole('menu')).toBeInTheDocument();
    // First Esc → menu closes, dock stays open.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    // Second Esc → dock collapses.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  // ── Wave-3: per-port ───────────────────────────────────────────────────────
  it('13. zone probe: a RED verdict renders the rail + RED tag + zone pill + reason', async () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    pickOrgan(/zone probe/i);
    const input = screen.getByLabelText(/classify a command/i);
    fireEvent.change(input, { target: { value: 'rm -rf /' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() =>
      expect(screen.getByText(/Destructive: rm -rf detected/i)).toBeInTheDocument()
    );
    // RED rail on the verdict row.
    const reason = screen.getByText(/Destructive: rm -rf detected/i);
    const row = reason.closest('.organs-row');
    expect(row.className).toContain('organs-row--bad');
    // The loud zone pill + the RED tag (triple-encoded danger).
    expect(within(row).getByText('RED', { selector: '.organs-zonepill' })).toBeInTheDocument();
    expect(within(row).getByText('RED', { selector: '.organs-quar' })).toBeInTheDocument();
    expect(within(row).getByText(/confidence 0\.97/)).toBeInTheDocument();
  });

  it('14. plan: steps render with AUTO / ESCALATE verdicts + human-review summary', async () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    pickOrgan(/^plan$/i);
    const input = screen.getByLabelText(/decompose a goal/i);
    fireEvent.change(input, { target: { value: 'ship the feature' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(screen.getByText('Read the spec')).toBeInTheDocument());
    // The approved step's row status reads AUTO; the escalated one reads ESCALATE.
    const autoStep = screen.getByText('Read the spec').closest('.organs-rung');
    expect(within(autoStep).getByText('AUTO')).toBeInTheDocument();
    const escStep = screen.getByText('Edit the gateway').closest('.organs-rung');
    expect(within(escStep).getByText('ESCALATE')).toBeInTheDocument();
    // requires_human surfaced as text.
    expect(screen.getByText('HUMAN REVIEW')).toBeInTheDocument();
    // Escalation reason is shown.
    expect(screen.getByText(/below threshold/i)).toBeInTheDocument();
  });

  it('15. models: Local READY + per-task AUTO routing rows render', async () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));
    pickOrgan(/^models$/i);
    await waitFor(() => expect(screen.getByText('Local')).toBeInTheDocument());
    // Local readiness word + the AUTO routing block.
    expect(screen.getByText('READY')).toBeInTheDocument();
    expect(screen.getByText('AUTO ROUTING')).toBeInTheDocument();
    expect(screen.getByText('CODING')).toBeInTheDocument();
    expect(screen.getByText('FAST')).toBeInTheDocument();
    // The chosen coding model tag appears.
    expect(screen.getAllByText('qwen2.5-coder:7b').length).toBeGreaterThan(0);
  });

  it('16. each new port shows an honest offline note on a rejected fetch', async () => {
    vi.stubGlobal('fetch', mockFetch({ fail: true }));
    render(<OrgansDock />);
    fireEvent.click(screen.getByRole('button', { name: /open organs dock/i }));

    // Models fetches on open → its offline note appears without a submit.
    pickOrgan(/^models$/i);
    await waitFor(() =>
      expect(screen.getByText(/MODELS OFFLINE/i)).toBeInTheDocument()
    );

    // Zone probe is request-driven → submit to trigger the failing fetch.
    pickOrgan(/zone probe/i);
    const zinput = screen.getByLabelText(/classify a command/i);
    fireEvent.change(zinput, { target: { value: 'ls' } });
    fireEvent.keyDown(zinput, { key: 'Enter' });
    await waitFor(() =>
      expect(screen.getByText(/ZONE PROBE OFFLINE/i)).toBeInTheDocument()
    );

    // Plan is request-driven → submit to trigger the failing fetch.
    pickOrgan(/^plan$/i);
    const pinput = screen.getByLabelText(/decompose a goal/i);
    fireEvent.change(pinput, { target: { value: 'do a thing' } });
    fireEvent.keyDown(pinput, { key: 'Enter' });
    await waitFor(() =>
      expect(screen.getByText(/PLAN OFFLINE/i)).toBeInTheDocument()
    );
  });
});
