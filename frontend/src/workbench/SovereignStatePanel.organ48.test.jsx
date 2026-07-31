import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import SovereignStatePanel, { TruthfulMirrorAuthority } from './SovereignStatePanel';

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

describe('Phase 2 organ 48 TruthfulMirrorAuthority reachability', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((url) => {
      const path = String(url);
      if (path.includes('/api/v1/mirror/governance')) {
        return jsonOk({ constitution: { digest: 'abc' }, emergencyStop: { engaged: false } });
      }
      if (path.includes('/api/v1/mirror/executor')) {
        return jsonOk({ executor: { configured: true } });
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

  it('panel load reaches TruthfulMirrorAuthority on the live singleton path', async () => {
    const normalizeGov = vi.spyOn(TruthfulMirrorAuthority.prototype, 'normalizeGovernance');
    const normalizeExec = vi.spyOn(TruthfulMirrorAuthority.prototype, 'normalizeExecutor');
    const allUnavailable = vi.spyOn(TruthfulMirrorAuthority.prototype, 'allUnavailable');

    render(<SovereignStatePanel />);

    await waitFor(() => {
      expect(normalizeGov).toHaveBeenCalled();
      expect(normalizeExec).toHaveBeenCalled();
      expect(allUnavailable).toHaveBeenCalled();
    });

    // Must not be a construct-in-test authority: the panel's module singleton
    // is what invoked these methods during load().
    expect(normalizeGov.mock.instances.length).toBeGreaterThan(0);
  });
});
