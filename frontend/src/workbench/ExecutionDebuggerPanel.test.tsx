import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ExecutionDebuggerPanel from './ExecutionDebuggerPanel';

describe('ExecutionDebuggerPanel', () => {
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
    render(<ExecutionDebuggerPanel />);
    expect(screen.getByText('Loading state...')).toBeInTheDocument();
  });

  it('renders state on successful load from the real backend shape', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        missions: [{ missionId: 'm-999', status: 'completed' }],
        count: 1,
        steppable: false,
        note: 'Council missions execute atomically; there is no interruptible step-machine to pause/resume.',
      }),
    });

    render(<ExecutionDebuggerPanel />);

    const preElement = await screen.findByText(/m-999/);
    expect(preElement).toBeInTheDocument();
    expect(preElement.textContent).toContain('completed');
  });

  it('disables Step/Resume and explains why when the backend reports non-steppable', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        missions: [],
        count: 0,
        steppable: false,
        note: 'Council missions execute atomically; there is no interruptible step-machine to pause/resume.',
      }),
    });

    render(<ExecutionDebuggerPanel />);

    await waitFor(() => {
      expect(screen.getByText(/no interruptible step-machine/)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Mission ID');
    fireEvent.change(input, { target: { value: 'm-123' } });

    expect(screen.getByText('Step').closest('button')).toBeDisabled();
    expect(screen.getByText('Resume').closest('button')).toBeDisabled();
    // Only the initial GET fired -- no phantom POST to a non-functional action.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
