import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SovereignStatePanel, { SovereignHeartbeatSurfaceAuthority } from './SovereignStatePanel';

vi.mock('../superbrain/lib/aiosAdapter', () => ({
  approveFactProposal: vi.fn(),
  fetchPendingFacts: vi.fn().mockResolvedValue([]),
  rejectFactProposal: vi.fn(),
}));

function jsonOk(body) {
  return Promise.resolve({
    ok: true,
    json: async () => body,
  });
}

describe('Phase 2 organ 51 SovereignHeartbeatSurfaceAuthority reachability', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((url) => {
      const path = String(url);
      if (path.includes('/api/v1/mirror/governance')) {
        return jsonOk({
          emergencyStop: {
            engaged: {
              value: false,
              status: 'measured',
              measured_at: '2026-07-31T00:00:00Z',
              source: 'test',
              freshness: 0,
            },
          },
        });
      }
      if (path.includes('/curriculum/proposals')) {
        return jsonOk({ proposals: [] });
      }
      return jsonOk({});
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('panel render reaches SovereignHeartbeatSurfaceAuthority.badge', async () => {
    const badge = vi.spyOn(SovereignHeartbeatSurfaceAuthority.prototype, 'badge');

    render(<SovereignStatePanel />);

    await waitFor(() => {
      expect(badge).toHaveBeenCalled();
    });

    expect(badge.mock.results.at(-1)?.value).toEqual({
      className: 'ok',
      text: 'operational',
    });
  });

  it('does not treat a swallowed fact-read failure as an empty sovereign ledger', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    render(<SovereignStatePanel />);

    await waitFor(() => {
      expect(screen.getByText('Sovereign state link offline')).toBeInTheDocument();
    });
    expect(screen.queryByText(/0 observed/)).not.toBeInTheDocument();
    expect(screen.queryByText('Nothing awaiting consumption right now.')).not.toBeInTheDocument();
    expect(screen.queryByText(/Quarantine is empty/)).not.toBeInTheDocument();
  });

  it('does not turn incomplete v10 records into confirmed zeroes', async () => {
    globalThis.fetch = vi.fn((url) => {
      if (String(url).includes('/api/v1/v10/status')) {
        return jsonOk({
          localOnly: true,
          constitution: { frozenCoreProtected: true },
          vulture: { lastScan: { findingCount: 2 } },
          ecosystem: { lastScan: { findingCount: 1 } },
          councilMemory: {},
          symbolRepoMap: { activation: 'proposal/evidence', lastScan: {} },
          metaLoop: { safetyStatus: 'ok' },
        });
      }
      if (String(url).includes('/curriculum/proposals')) return jsonOk({});
      return jsonOk({});
    });

    render(<SovereignStatePanel />);

    expect(await screen.findByText(/Sovereign Organism v10/)).toBeInTheDocument();
    expect(screen.getByText(/2 finding\(s\) · cloud calls unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/1 finding\(s\) · cloud calls unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/castes unavailable · frozen core protected/)).toBeInTheDocument();
    expect(screen.getByText(/deliberation\(s\) unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/symbols unavailable · proposal\/evidence/)).toBeInTheDocument();
    expect(screen.getByText(/ok · proposal\(s\) unavailable/)).toBeInTheDocument();
    expect(screen.getByText('scan state unavailable')).toBeInTheDocument();
    expect(screen.getByText(/unknown · cloud posture unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/run state unavailable/)).toBeInTheDocument();
    expect(screen.getByText('Pheromones').parentElement).toHaveTextContent('unavailable');
    expect(screen.getByText('Caste contracts').parentElement).toHaveTextContent('unavailable');
    expect(screen.getByText('Autonomy ledger unavailable.')).toBeInTheDocument();
    expect(screen.getByText('Skill trails are unavailable.')).toBeInTheDocument();
    expect(screen.getByText('Curriculum proposals are unavailable.')).toBeInTheDocument();
  });

  it('does not turn a missing pheromone strength into a zero-percent signal', async () => {
    globalThis.fetch = vi.fn((url) => {
      const path = String(url);
      if (path.includes('/api/v1/pheromones/surface')) {
        return jsonOk({
          pheromones: [{ id: 'trail-1', type: 'skill', resource: 'memory-search' }],
        });
      }
      if (path.includes('/curriculum/proposals')) return jsonOk({ proposals: [] });
      return jsonOk({});
    });

    render(<SovereignStatePanel />);

    expect(await screen.findByText(/skill · memory-search · strength unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/skill · memory-search · 0%/)).not.toBeInTheDocument();
  });
});
