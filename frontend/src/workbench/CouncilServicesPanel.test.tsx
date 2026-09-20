import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CouncilServicesPanel from './CouncilServicesPanel';

describe('CouncilServicesPanel', () => {
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

  it('renders the backend health-map envelope without losing service identity', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        services: {
          planner: { name: 'planner', alive: true, queue_depth: 2, processed: 4, errors: 1 },
        },
      }),
    });

    render(<CouncilServicesPanel />);

    await waitFor(() => {
      expect(screen.getByText('planner')).toBeInTheDocument();
      expect(screen.getByText('queue 2 · processed 4 · errors 1')).toBeInTheDocument();
    });
  });

  it('does not turn a malformed services envelope into an empty service list', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    render(<CouncilServicesPanel />);

    await waitFor(() => {
      expect(screen.getByText('Council services unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No services found.')).not.toBeInTheDocument();
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
