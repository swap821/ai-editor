import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SovereigntyControls from './SovereigntyControls';

describe('SovereigntyControls', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
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
          body: JSON.stringify({ resource: '/src/App.jsx', type: 'success', amount: 1.0 })
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Pheromone deposit triggered on /src/App.jsx')).toBeInTheDocument();
    });
  });
});
