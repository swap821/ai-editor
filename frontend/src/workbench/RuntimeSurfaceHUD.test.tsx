import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import RuntimeSurfaceHUD from './RuntimeSurfaceHUD';

describe('RuntimeSurfaceHUD', () => {
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
    render(<RuntimeSurfaceHUD />);
    expect(screen.getByText('Scanning surface...')).toBeInTheDocument();
  });

  it('renders signals on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        signals: [
          { signal_id: 7, stype: 'progress-update', resource: 'mission-1', worker_id: 'worker-1', ttl_seconds: 30, payload: { foo: 'bar' }, created_at: 123.4 }
        ],
      }),
    });

    render(<RuntimeSurfaceHUD />);
    
    await waitFor(() => {
      expect(screen.getAllByText('progress-update')[0]).toBeInTheDocument();
      expect(screen.getByText(/foo/)).toBeInTheDocument();
    });
  });

  it('does not turn a malformed surface envelope into a clean surface', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total: 0 }),
    });

    render(<RuntimeSurfaceHUD />);

    await waitFor(() => {
      expect(screen.getByText('Runtime surface unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('Surface is clean.')).not.toBeInTheDocument();
  });

  it('submits a new signal', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ signals: [] }),
    });

    render(<RuntimeSurfaceHUD />);

    fireEvent.change(screen.getByLabelText('Signal type'), { target: { value: 'progress-update' } });
    fireEvent.change(screen.getByLabelText('Signal resource'), { target: { value: 'mission-1' } });
    fireEvent.change(screen.getByLabelText('Signal worker'), { target: { value: 'worker-1' } });
    
    const input = screen.getByPlaceholderText(/{"type": "event", "data": 123}/);
    fireEvent.change(input, { target: { value: '{"type": "custom", "val": 42}' } });
    
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ signals: [] }) });

    const submitBtn = screen.getByText('Emit to Surface');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/runtime/surface/emit'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            stype: 'progress-update',
            resource: 'mission-1',
            workerId: 'worker-1',
            ttlSeconds: 30,
            payload: { type: 'custom', val: 42 },
          })
        })
      );
    });
  });

  it('handles sweep action', async () => {
    window.confirm = vi.fn(() => true);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        signals: [
          { signal_id: 123, stype: 'progress-update', resource: 'mission-1', worker_id: 'worker-1', ttl_seconds: 30, payload: {}, created_at: 123.4 }
        ],
      }),
    });

    render(<RuntimeSurfaceHUD />);
    
    await waitFor(() => {
      expect(screen.getByText('progress-update')).toBeInTheDocument();
    });

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ signals: [] }) });
    
    const sweepBtn = screen.getByText(/Sweep Surface/);
    fireEvent.click(sweepBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/runtime/surface/sweep'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });
});
