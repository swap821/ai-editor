import { render, screen, waitFor } from '@testing-library/react';
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
    globalThis.fetch = vi.fn();
  });

  it('renders loading state and fetches default node', async () => {
    globalThis.fetch.mockImplementation(() => new Promise(() => {})); // pending
    render(<StigmergyPanel onClose={vi.fn()} />);
    
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('start=system'));
  });

  it('renders graph edges on success', async () => {
    globalThis.fetch.mockResolvedValueOnce({
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
