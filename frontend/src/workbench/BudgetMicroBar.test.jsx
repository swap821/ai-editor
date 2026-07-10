import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import BudgetMicroBar from './BudgetMicroBar';
import React from 'react';

describe('BudgetMicroBar', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: 'normal',
        cloud_calls: 3,
        estimated_cost: 12.5,
        worker_count: 2,
        cpu_pressure: 0.42,
        memory_pressure: 0.31,
        cloud_allowed: true,
        reason: 'cloud eligible subject to per-mission policy',
      }),
    });
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('fetches and renders the real resource status', async () => {
    render(<BudgetMicroBar />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/resource/status'),
        expect.objectContaining({ credentials: 'include' })
      );
      expect(screen.getByText('normal')).toBeInTheDocument();
      expect(screen.getByText('$12.50')).toBeInTheDocument();
    });
  });

  it('expands to show real, live resource fields (not a fabricated breakdown)', async () => {
    render(<BudgetMicroBar />);

    await waitFor(() => expect(screen.getByText('normal')).toBeInTheDocument());

    fireEvent.click(screen.getByText('normal'));

    expect(screen.getByText('Live Resource Status')).toBeInTheDocument();
    expect(screen.getByText('Cloud calls')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Workers')).toBeInTheDocument();
    expect(screen.getByText('42%')).toBeInTheDocument();
    expect(screen.getByText('31%')).toBeInTheDocument();
    expect(screen.getByText('cloud eligible subject to per-mission policy')).toBeInTheDocument();
  });
});
