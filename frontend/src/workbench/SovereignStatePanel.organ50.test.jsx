import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import SovereignStatePanel, { ProvenanceExplanationSurfaceAuthority } from './SovereignStatePanel';

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

describe('Phase 2 organ 50 ProvenanceExplanationSurfaceAuthority reachability', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((url) => {
      const path = String(url);
      if (path.includes('/api/v1/mirror/governance')) {
        return jsonOk({
          routingDecisions: [{ provider: 'ollama' }],
          privacyAudits: [{ provider: 'ollama', redacted_paths: 0 }],
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

  it('panel render reaches ProvenanceExplanationSurfaceAuthority.project', async () => {
    const project = vi.spyOn(ProvenanceExplanationSurfaceAuthority.prototype, 'project');

    render(<SovereignStatePanel />);

    await waitFor(() => {
      expect(project).toHaveBeenCalled();
    });

    const projected = project.mock.results.at(-1)?.value;
    expect(projected.routingDecisions).toHaveLength(1);
    expect(projected.privacyAudits).toHaveLength(1);
  });
});
