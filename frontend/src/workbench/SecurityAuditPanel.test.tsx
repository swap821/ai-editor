import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SecurityAuditPanel from './SecurityAuditPanel';

describe('SecurityAuditPanel', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    fetchMock.mockImplementation(() => new Promise(() => {})); 
    render(<SecurityAuditPanel />);
    expect(screen.getByText('Loading audit log...')).toBeInTheDocument();
  });

  it('renders log on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        log: [
          { event: 'SECURITY_SCAN', timestamp: '2026-07-09T10:00:00Z', details: 'Passed' }
        ],
      }),
    });

    render(<SecurityAuditPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('SECURITY_SCAN')).toBeInTheDocument();
      expect(screen.getByText('Passed')).toBeInTheDocument();
    });
  });

  it('handles sandbox clear', async () => {
    window.confirm = vi.fn(() => true);
    window.alert = vi.fn();

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        log: [],
      }),
    });

    render(<SecurityAuditPanel />);
    
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ log: [] }) });

    const btn = screen.getByText('Clear Sandbox');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/security/sandbox/clear'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });
});
