import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MemoryBrowser from './MemoryBrowser';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  )
}));

describe('MemoryBrowser', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it('renders loading state initially', () => {
    // Need an unresolved promise so it stays loading
    global.fetch.mockImplementation(() => new Promise(() => {}));
    
    render(<MemoryBrowser onClose={vi.fn()} />);
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Loading memories.../i)).toBeInTheDocument();
  });

  it('renders experiences on success', async () => {
    const fakeExperiences = [
      JSON.stringify({ task_id: 'TASK-1', goal: 'Test goal', outcome: 'success', lessons: 'Learned A' }),
      JSON.stringify({ task_id: 'TASK-2', goal: 'Another goal', outcome: 'failure', lessons: 'Learned B' })
    ].join('\n');

    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ content: fakeExperiences })
    });

    render(<MemoryBrowser onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('TASK-1')).toBeInTheDocument();
      expect(screen.getByText('TASK-2')).toBeInTheDocument();
    });
  });

  it('renders error on failure', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'));

    render(<MemoryBrowser onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/Error: Network error/i)).toBeInTheDocument();
    });
  });
});
