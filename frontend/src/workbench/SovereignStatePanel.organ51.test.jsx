import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
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
});
