import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchAlignmentEvaluation,
  submitAlignmentFeedback,
} from './alignmentEvaluation';

describe('alignment evaluation API', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('fetches the read-only evaluation summary', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ total_turns: 4, automatic_policy_updates: false }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAlignmentEvaluation();

    expect(result.total_turns).toBe(4);
    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/alignment/evaluation');
  });

  it('submits explicit human feedback for a session', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ observationId: 7 }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    await submitAlignmentFeedback('session-1', {
      observationId: 7,
      outcome: 'misaligned',
      issues: ['wrong_goal'],
    });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      sessionId: 'session-1',
      observationId: 7,
      outcome: 'misaligned',
      issues: ['wrong_goal'],
    });
  });
});
