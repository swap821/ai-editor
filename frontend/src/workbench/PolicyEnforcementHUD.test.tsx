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
          { id: 'pol_12345678', text: 'Never delete user data', status: 'enacted' },
          { id: 'pol_87654321', text: 'Always use JSON', status: 'proposed' }
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
        policies: [{ id: 'new_pol', text: 'No internet access', status: 'proposed' }]
      }),
    });

    const submitBtn = screen.getByText('Submit Proposal');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/policy/propose'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ policyText: 'No internet access' })
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
          { id: 'pol_123', text: 'Test Policy', status: 'proposed' }
        ],
      }),
    });

    render(<PolicyEnforcementHUD />);
    
    await waitFor(() => {
      expect(screen.getByText('Test Policy')).toBeInTheDocument();
    });

    // Handle vote
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ policies: [] }) });
    
    const voteBtn = screen.getByText(/Vote Approve/);
    fireEvent.click(voteBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/policy/pol_123/vote'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });
});
