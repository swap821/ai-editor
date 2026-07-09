import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CouncilServicesPanel from './CouncilServicesPanel';

describe('CouncilServicesPanel', () => {
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
    render(<CouncilServicesPanel />);
    expect(screen.getByText('Loading services...')).toBeInTheDocument();
  });

  it('renders services on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        services: [
          { name: 'Memory Consolidation', running: true, description: 'Moves facts to LTM' },
          { name: 'Fact Checker', running: false, description: 'Checks internet' }
        ],
      }),
    });

    render(<CouncilServicesPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('Memory Consolidation')).toBeInTheDocument();
      expect(screen.getByText('Fact Checker')).toBeInTheDocument();
    });
  });

  it('toggles a service', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        services: [{ name: 'TestService', running: false, description: 'desc' }],
      }),
    });

    render(<CouncilServicesPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('TestService')).toBeInTheDocument();
    });

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ services: [] }) });

    const toggleBtn = screen.getByLabelText('Toggle TestService');
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/council/services/TestService/start'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('handles mission rejection', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ services: [] }),
    });

    render(<CouncilServicesPanel />);
    
    const idInput = screen.getByPlaceholderText('Mission ID');
    const reasonInput = screen.getByPlaceholderText('Rejection Reason');
    
    fireEvent.change(idInput, { target: { value: 'm-123' } });
    fireEvent.change(reasonInput, { target: { value: 'Too risky' } });
    
    window.alert = vi.fn();
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    const btn = screen.getByText('Force Reject');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/council/reject'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ missionId: 'm-123', reason: 'Too risky' })
        })
      );
    });
    
    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith('Mission rejected.');
    });
  });
});
