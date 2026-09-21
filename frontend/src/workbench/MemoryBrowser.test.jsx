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
    globalThis.fetch = vi.fn();
  });

  it('renders loading state initially', () => {
    // Need an unresolved promise so it stays loading
    globalThis.fetch.mockImplementation(() => new Promise(() => {}));
    
    render(<MemoryBrowser onClose={vi.fn()} />);
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Loading records/i)).toBeInTheDocument();
  });

  it('renders experiences on success', async () => {
    const fakeExperiences = [
      JSON.stringify({ task_id: 'TASK-1', goal: 'Test goal', outcome: 'success', lessons: 'Learned A' }),
      JSON.stringify({ task_id: 'TASK-2', goal: 'Another goal', outcome: 'failure', lessons: 'Learned B' })
    ].join('\n');

    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ content: fakeExperiences })
    });

    render(<MemoryBrowser onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('TASK-1')).toBeInTheDocument();
      expect(screen.getByText('TASK-2')).toBeInTheDocument();
      expect(screen.getByText('Learned A')).toBeInTheDocument();
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/files/read'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('experiences.jsonl'),
      }),
    );
  });

  it('keeps valid records visible while flagging malformed ledger lines', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ content: '{not-json}\n{"task_id":"TASK-3","lessons":"Keep the record"}' }),
    });

    render(<MemoryBrowser onClose={vi.fn()} />);

    expect(await screen.findByText('TASK-3')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('1 ledger line could not be parsed');
  });

  it('renders error on failure', async () => {
    globalThis.fetch.mockRejectedValueOnce(new Error('Network error'));

    render(<MemoryBrowser onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/Local service could not be reached/i)).toBeInTheDocument();
    });
  });
});
