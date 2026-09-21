import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AlignmentHUD from './AlignmentHUD';

const alignmentSummary = (overrides = {}) => ({
  total_turns: 2,
  corrected_turns: 1,
  correction_rate: 0.5,
  human_feedback_count: 1,
  positive_feedback_rate: 1,
  ask_rate: 0.5,
  state_assumptions_rate: 0,
  outcomes: { aligned: 1 },
  by_intent: { execute: 2 },
  by_communication_mode: { direct: 2 },
  by_ambiguity_action: { ask: 1, proceed: 1 },
  corrected_fields: { intent: 1 },
  issues: {},
  repeated_patterns: [],
  recent: [],
  automatic_policy_updates: false,
  ...overrides,
});

describe('AlignmentHUD', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    fetchMock.mockImplementation(() => new Promise(() => {})); 
    render(<AlignmentHUD />);
    expect(screen.getByText('Loading alignment...')).toBeInTheDocument();
  });

  it('renders state on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => alignmentSummary(),
    });

    render(<AlignmentHUD />);
    
    await waitFor(() => {
      expect(screen.getByText(/"total_turns": 2/)).toBeInTheDocument();
    });
  });

  it('loads from the real backend alignment-evaluation endpoint', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => alignmentSummary(),
    });

    render(<AlignmentHUD />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/alignment/evaluation'),
        expect.objectContaining({ credentials: 'include' })
      );
    });
  });

  it('keeps malformed evaluation envelopes unavailable instead of rendering an empty summary', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    render(<AlignmentHUD />);

    await waitFor(() => {
      expect(screen.getByText('Alignment data unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No alignment data.')).not.toBeInTheDocument();
  });

  it('handles sync action by refetching the evaluation summary (no sync endpoint exists)', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => alignmentSummary({ total_turns: 1, positive_feedback_rate: 0 }),
    });

    render(<AlignmentHUD />);

    await waitFor(() => {
      expect(screen.getByText(/"total_turns": 1/)).toBeInTheDocument();
    });

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => alignmentSummary({ total_turns: 2 }) });

    const syncBtn = screen.getByText(/Sync Alignment/);
    fireEvent.click(syncBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining('/api/v1/alignment/evaluation'),
        expect.objectContaining({ credentials: 'include' })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Refreshed')).toBeInTheDocument();
    });
  });

  it('does not claim a refresh succeeded when the evaluation request fails', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => alignmentSummary(),
    });

    render(<AlignmentHUD />);

    await waitFor(() => {
      expect(screen.getByText(/"total_turns": 2/)).toBeInTheDocument();
    });

    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 });
    fireEvent.click(screen.getByText(/Sync Alignment/));

    await waitFor(() => {
      expect(screen.getByText('Refresh failed: Alignment data offline')).toBeInTheDocument();
    });
    expect(screen.queryByText('Refreshed')).not.toBeInTheDocument();
  });
});
