import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PolicyEnforcementHUD from './PolicyEnforcementHUD';

describe('PolicyEnforcementHUD', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    fetchMock.mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<PolicyEnforcementHUD />);
    expect(screen.getByText('Syncing ledger...')).toBeInTheDocument();
  });

  it('renders policy chain on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        policies: [
          { policy_id: 'pol_12345678', constraint: 'Never delete user data', status: 'enacted', version: 1, proposed_by: 'operator', enacted_at: null },
          { policy_id: 'pol_87654321', constraint: 'Always use JSON', status: 'proposed', version: 1, proposed_by: 'operator', enacted_at: null }
        ],
      }),
    });

    render(<PolicyEnforcementHUD />);
    
    await waitFor(() => {
      expect(screen.getByText('pol_1234')).toBeInTheDocument();
      expect(screen.getByText('pol_8765')).toBeInTheDocument();
    });
    
    expect(screen.getByText('Never delete user data')).toBeInTheDocument();
    expect(screen.getByText('Always use JSON')).toBeInTheDocument();
  });

  it('does not turn a malformed policy envelope into an empty active chain', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    render(<PolicyEnforcementHUD />);

    await waitFor(() => {
      expect(screen.getByText('Policy chain unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No policies active in the chain.')).not.toBeInTheDocument();
  });

  it('submits a new policy proposal', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ policies: [] }),
    });

    render(<PolicyEnforcementHUD />);
    
    const input = screen.getByPlaceholderText(/Never write to the/);
    fireEvent.change(input, { target: { value: 'No internet access' } });
    
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Proposed' }),
    });

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        policies: [{ policy_id: 'new_pol', constraint: 'No internet access', status: 'proposed', version: 1, proposed_by: 'operator', enacted_at: null }]
      }),
    });

    const submitBtn = screen.getByText('Submit Proposal');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/policy/propose'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ constraint: 'No internet access' })
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('No internet access')).toBeInTheDocument();
    });
  });

  it('handles vote and enact actions', async () => {
    window.confirm = vi.fn(() => true);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        policies: [
          { policy_id: 'pol_123', constraint: 'Test Policy', status: 'proposed', version: 1, proposed_by: 'operator', enacted_at: null }
        ],
      }),
    });

    render(<PolicyEnforcementHUD />);
    
    await waitFor(() => {
      expect(screen.getByText('Test Policy')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Policy voting queen'), { target: { value: 'planner' } });
    fireEvent.change(screen.getByLabelText('Policy vote reason'), { target: { value: 'Reviewed proposal' } });

    // Handle vote
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ policies: [] }) });
    
    const voteBtn = screen.getByText(/Vote Approve/);
    fireEvent.click(voteBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/policy/pol_123/vote'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ queen: 'planner', approve: true, reason: 'Reviewed proposal' }),
        })
      );
    });
  });
});
