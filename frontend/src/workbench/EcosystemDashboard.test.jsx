import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EcosystemDashboard from './EcosystemDashboard';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  )
}));

describe('EcosystemDashboard', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it('renders loading state initially', () => {
    global.fetch.mockImplementation(() => new Promise(() => {}));
    render(<EcosystemDashboard onClose={vi.fn()} />);
    
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Scanning ecosystem.../i)).toBeInTheDocument();
  });

  it('renders metrics on success', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        memory_integration_score: 0.95,
        fact_consistency: 0.99,
        active_models: ['llama3.1', 'qwen2.5'],
        tasks_completed: 42,
        tasks_failed: 1
      })
    });

    render(<EcosystemDashboard onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('95.0%')).toBeInTheDocument();
      expect(screen.getByText('99.0%')).toBeInTheDocument();
      expect(screen.getByText('llama3.1')).toBeInTheDocument();
      expect(screen.getByText(/Completed: 42/i)).toBeInTheDocument();
    });
  });
});
