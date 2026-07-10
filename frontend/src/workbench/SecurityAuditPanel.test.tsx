import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SecurityAuditPanel from './SecurityAuditPanel';

describe('SecurityAuditPanel', () => {
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
    render(<SecurityAuditPanel />);
    expect(screen.getByText('Loading audit log...')).toBeInTheDocument();
  });

  it('renders log on successful load from the real audit-ledger shape', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        entries: [
          { entryId: 1, actor: 'operator', zone: 'GREEN', timestamp: '2026-07-09T10:00:00Z', payload: 'Passed scan' }
        ],
        chainValid: true,
      }),
    });

    render(<SecurityAuditPanel />);

    await waitFor(() => {
      expect(screen.getByText(/operator — GREEN/)).toBeInTheDocument();
      expect(screen.getByText('Passed scan')).toBeInTheDocument();
      expect(screen.getByText(/Hash chain: valid/)).toBeInTheDocument();
    });
  });

  it('handles sandbox clear by POSTing an explicit confirm flag', async () => {
    window.confirm = vi.fn(() => true);
    window.alert = vi.fn();

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ entries: [], chainValid: true }),
    });

    render(<SecurityAuditPanel />);

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'cleared', removedCount: 3 }) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], chainValid: true }) });

    const btn = screen.getByText('Clear Sandbox');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/security/sandbox/clear'),
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ confirm: true }) })
      );
    });
  });
});
