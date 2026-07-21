import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import CouncilDashboard from './CouncilDashboard';

// Fake timers are active for these tests (to control the 15s poll), so
// Testing Library's `waitFor` (which polls with real timers) cannot be used.
// Flush microtasks explicitly under `act` instead.
async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

// W4.2 (SYN-21): refresh-icon spin fires ONLY on a manual refresh click; the
// 15s background poll must never spin it. W4.4 (SYN-25): mission-detail
// cross-fades via a key={missionId} remount on selection change.

const missionA = {
  missionId: 'mission-a',
  mission: 'Mission A goal text.',
  status: 'completed',
  recommendation: 'approve',
  risk: 'GREEN',
  approvalNeeded: false,
  rollbackAvailable: false,
  filesTouched: [],
  blockedAttempts: 0,
  councilVerdicts: [],
  modelRouting: { provider: 'ollama', used_cloud: false, fallback_used: false },
  pendingApprovals: [],
  kingDecision: null,
};

const missionB = {
  ...missionA,
  missionId: 'mission-b',
  mission: 'Mission B goal text.',
};

function detailFor(mission: typeof missionA) {
  return {
    missionId: mission.missionId,
    report: {
      mission_id: mission.missionId,
      mission: mission.mission,
      status: mission.status,
      council_summary: { council_verdicts: [], model_routing: mission.modelRouting },
      recommendation: mission.recommendation,
      risk: mission.risk,
      files: [],
      approval_needed: false,
      rollback_available: false,
      rollback_id: null,
    },
    ledger: { blocked_attempts: [] },
    pendingApprovals: [],
    kingDecision: null,
  };
}

describe('CouncilDashboard W4 motion niceties', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock = vi.fn((url: string) => {
      if (url.includes('/api/v1/council/missions/mission-a')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(detailFor(missionA)) });
      }
      if (url.includes('/api/v1/council/missions/mission-b')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(detailFor(missionB)) });
      }
      if (url.includes('/api/v1/council/missions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ missions: [missionA, missionB], count: 2 }),
        });
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('spins the refresh icon only for a manual click, never for the 15s background poll', async () => {
    render(<CouncilDashboard />);
    await flush();

    expect(screen.getAllByText('Mission A goal text.').length).toBeGreaterThan(0);

    const refreshBtn = screen.getByRole('button', { name: 'Refresh council reports' });
    expect(refreshBtn.className).not.toContain('is-refreshing');

    // Advance past TWO background poll cycles (15s each) without ever clicking
    // the button — the poll calls the same loadMissions() but must never spin.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(refreshBtn.className).not.toContain('is-refreshing');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(refreshBtn.className).not.toContain('is-refreshing');

    // Now a MANUAL click must spin it immediately, then clear once resolved.
    let resolveManual: (() => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveManual = () =>
            resolve({ ok: true, json: () => Promise.resolve({ missions: [missionA, missionB], count: 2 }) });
        }),
    );

    fireEvent.click(refreshBtn);
    expect(refreshBtn.className).toContain('is-refreshing');

    await act(async () => {
      resolveManual?.();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(refreshBtn.className).not.toContain('is-refreshing');
  });

  it('remounts the detail section (key=missionId) when the selected mission changes', async () => {
    render(<CouncilDashboard />);
    await flush();

    expect(screen.getAllByText('Mission A goal text.').length).toBeGreaterThan(0);

    const detailBefore = document.querySelector('.council-dashboard__detail');
    expect(detailBefore).toBeTruthy();

    const missionBCard = screen.getByText('Mission B goal text.').closest('button');
    expect(missionBCard).toBeTruthy();
    fireEvent.click(missionBCard as HTMLElement);
    await flush();

    expect(screen.getAllByText('Mission B goal text.').length).toBeGreaterThan(0);

    const detailAfter = document.querySelector('.council-dashboard__detail');
    expect(detailAfter).toBeTruthy();
    // A key-driven remount produces a NEW DOM node, not an in-place mutation.
    expect(detailAfter).not.toBe(detailBefore);
  });
});
