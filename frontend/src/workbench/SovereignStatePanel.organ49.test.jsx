import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import SovereignStatePanel, { ApprovalDecisionSurfaceAuthority } from './SovereignStatePanel';

vi.mock('../superbrain/lib/aiosAdapter', () => ({
  approveFactProposal: vi.fn(),
  fetchPendingFacts: vi.fn().mockResolvedValue([{ id: 'fact-1' }]),
  rejectFactProposal: vi.fn(),
}));

function jsonOk(body) {
  return Promise.resolve({
    ok: true,
    json: async () => body,
  });
}

describe('Phase 2 organ 49 ApprovalDecisionSurfaceAuthority reachability', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((url) => {
      const path = String(url);
      if (path.includes('/curriculum/proposals')) {
        return jsonOk({ proposals: [{ fingerprint: 'skill-1' }] });
      }
      if (path.includes('/council/missions')) {
        return jsonOk({ missions: [{ pendingApprovals: [{ id: 'a1' }] }] });
      }
      if (path.includes('/self-analysis/proposals')) {
        return jsonOk({ proposals: [{ status: 'proposed' }] });
      }
      return jsonOk({});
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('panel render reaches ApprovalDecisionSurfaceAuthority.pendingCount', async () => {
    const pendingCount = vi.spyOn(ApprovalDecisionSurfaceAuthority.prototype, 'pendingCount');

    render(<SovereignStatePanel />);

    await waitFor(() => {
      expect(pendingCount).toHaveBeenCalled();
    });

    const lastArgs = pendingCount.mock.calls.at(-1)?.[0];
    expect(lastArgs.facts).toEqual([{ id: 'fact-1' }]);
    expect(lastArgs.curriculum).toEqual([{ fingerprint: 'skill-1' }]);
  });
});
