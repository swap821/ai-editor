import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SovereigntyControls from './SovereigntyControls';

describe('SovereigntyControls', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly', () => {
    render(<SovereigntyControls />);
    expect(screen.getByText('Trigger Hibernation')).toBeInTheDocument();
    expect(screen.getByText('Register Snapshot')).toBeInTheDocument();
  });

  it('handles hibernation trigger', async () => {
    window.confirm = vi.fn(() => true);
    
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Hibernation started' }),
    });

    render(<SovereigntyControls />);
    const btn = screen.getByText('Trigger Hibernation');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/hibernation/run'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Hibernation started')).toBeInTheDocument();
    });
  });

  it('handles pheromone injection', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Pheromone deposited' }),
    });

    render(<SovereigntyControls />);
    
    const resourceInput = screen.getByPlaceholderText(/Resource/);
    fireEvent.change(resourceInput, { target: { value: '/src/App.jsx' } });
    
    const depositBtn = screen.getByText(/Deposit/i, { selector: 'button' });
    fireEvent.click(depositBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/pheromones/deposit'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            resource: '/src/App.jsx',
            ptype: 'success-trail',
            strength: 1.0,
            payload: {},
          })
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Pheromone deposit triggered on /src/App.jsx')).toBeInTheDocument();
    });
  });

  it('reinforces an identified pheromone instead of sending a resource as its id', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ reinforced: true }),
    });

    render(<SovereigntyControls />);

    fireEvent.change(screen.getByPlaceholderText('Pheromone ID'), { target: { value: '42' } });
    fireEvent.click(screen.getByText(/Reinforce/i, { selector: 'button' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/pheromones/reinforce'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ pheromoneId: 42, boost: 0.2 }),
        }),
      );
    });
  });

  it('registers a rollback snapshot with the required identity fields', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ registered: true, snapshot_id: 'snapshot-1' }),
    });

    render(<SovereigntyControls />);

    fireEvent.change(screen.getByLabelText('Rollback snapshot ID'), { target: { value: 'snapshot-1' } });
    fireEvent.change(screen.getByLabelText('Rollback mission ID'), { target: { value: 'mission-1' } });
    fireEvent.change(screen.getByLabelText('Rollback workspace root'), { target: { value: 'C:/workspace' } });
    fireEvent.click(screen.getByText('Register Snapshot'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/runtime/rollbacks/register'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            snapshotId: 'snapshot-1',
            missionId: 'mission-1',
            workspaceRoot: 'C:/workspace',
            filesCovered: [],
            metadata: {},
          }),
        }),
      );
    });
  });
});
