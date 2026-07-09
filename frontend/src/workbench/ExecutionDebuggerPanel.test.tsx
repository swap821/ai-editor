import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ExecutionDebuggerPanel from './ExecutionDebuggerPanel';

describe('ExecutionDebuggerPanel', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    fetchMock.mockImplementation(() => new Promise(() => {})); 
    render(<ExecutionDebuggerPanel />);
    expect(screen.getByText('Loading state...')).toBeInTheDocument();
  });

  it('renders state on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'paused', mission: 'm-999' }),
    });

    render(<ExecutionDebuggerPanel />);
    
    const preElement = await screen.findByText(/m-999/);
    expect(preElement).toBeInTheDocument();
    expect(preElement.textContent).toContain('paused');
  });

  it('handles step action', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'paused' }),
    });

    render(<ExecutionDebuggerPanel />);
    
    const input = screen.getByPlaceholderText('Mission ID');
    fireEvent.change(input, { target: { value: 'm-123' } });
    
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'running' }) });

    const stepBtn = screen.getByText('Step');
    fireEvent.click(stepBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/execution/debugger/step'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ missionId: 'm-123' })
        })
      );
    });
  });

  it('handles resume action', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'paused' }),
    });

    render(<ExecutionDebuggerPanel />);
    
    const input = screen.getByPlaceholderText('Mission ID');
    fireEvent.change(input, { target: { value: 'm-123' } });
    
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'running' }) });

    const resumeBtn = screen.getByText('Resume');
    fireEvent.click(resumeBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/execution/debugger/resume'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ missionId: 'm-123' })
        })
      );
    });
  });
});
