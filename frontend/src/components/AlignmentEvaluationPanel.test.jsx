import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AlignmentEvaluationPanel from './AlignmentEvaluationPanel';

const SUMMARY = {
  total_turns: 10,
  corrected_turns: 2,
  correction_rate: 0.2,
  human_feedback_count: 4,
  positive_feedback_rate: 0.75,
  ask_rate: 0.1,
  state_assumptions_rate: 0.3,
  outcomes: { aligned: 3, misaligned: 1 },
  issues: { wrong_goal: 1 },
  corrected_fields: { goal: 2 },
  by_ambiguity_action: { proceed: 6, state_assumptions: 3, ask: 1 },
  repeated_patterns: [{ kind: 'corrected_field', name: 'goal', count: 3 }],
};

describe('AlignmentEvaluationPanel', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('renders aggregate human-alignment evidence and repeated candidates', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(SUMMARY),
    })));

    render(<AlignmentEvaluationPanel />);

    expect(await screen.findByText('10')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.getByText(/corrected field: goal \(3\)/i)).toBeInTheDocument();
    expect(screen.getByText(/never approves actions or automatically changes policy/i)).toBeInTheDocument();
  });

  it('refreshes evidence on operator request', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(SUMMARY),
    }));
    vi.stubGlobal('fetch', fetchMock);
    render(<AlignmentEvaluationPanel />);
    await screen.findByText('10');

    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
