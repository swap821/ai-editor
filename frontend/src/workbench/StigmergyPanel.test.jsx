import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StigmergyPanel from './StigmergyPanel';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  )
}));

describe('StigmergyPanel', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it('renders loading state and fetches default node', async () => {
    global.fetch.mockImplementation(() => new Promise(() => {})); // pending
    render(<StigmergyPanel onClose={vi.fn()} />);
    
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('start=system'));
  });

  it('renders graph edges on success', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        edges: [
          { subject: 'system', predicate: 'depends_on', object: 'database', depth: 1 },
          { subject: 'database', predicate: 'stores', object: 'users', depth: 2 }
        ]
      })
    });

    render(<StigmergyPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getAllByText(/system/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/depends_on/i)).toBeInTheDocument();
      expect(screen.getAllByText(/database/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/stores/i)).toBeInTheDocument();
    });
  });
});
