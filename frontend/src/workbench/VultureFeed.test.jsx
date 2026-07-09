import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import VultureFeed from './VultureFeed';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  )
}));

describe('VultureFeed', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it('renders loading state initially', () => {
    globalThis.fetch.mockImplementation(() => new Promise(() => {}));
    render(<VultureFeed onClose={vi.fn()} />);
    
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Monitoring security boundaries.../i)).toBeInTheDocument();
  });

  it('renders trails on success', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        trails: [
          { event: 'Unauthorized Access', action: 'block', details: 'Blocked attempt', agent: 'Agent X' }
        ]
      })
    });

    render(<VultureFeed onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/Unauthorized Access/i)).toBeInTheDocument();
      expect(screen.getByText(/Blocked attempt/i)).toBeInTheDocument();
      expect(screen.getByText(/Agent X/i)).toBeInTheDocument();
    });
  });
});
