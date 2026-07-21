import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AlignmentHUD from './AlignmentHUD';

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
      json: async () => ({ drift: 0.05, status: 'aligned' }),
    });

    render(<AlignmentHUD />);
    
    await waitFor(() => {
      expect(screen.getByText(/aligned/)).toBeInTheDocument();
    });
  });

  it('loads from the real backend alignment-evaluation endpoint', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ drift: 0.05, status: 'aligned' }),
    });

    render(<AlignmentHUD />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/alignment/evaluation'),
        expect.objectContaining({ credentials: 'include' })
      );
    });
  });

  it('handles sync action by refetching the evaluation summary (no sync endpoint exists)', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ drift: 0.1, status: 'drifting' }),
    });

    render(<AlignmentHUD />);

    await waitFor(() => {
      expect(screen.getByText(/drifting/)).toBeInTheDocument();
    });

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ drift: 0.0, status: 'aligned' }) });

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
});
