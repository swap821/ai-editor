import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import RuntimeSurfaceHUD from './RuntimeSurfaceHUD';

describe('RuntimeSurfaceHUD', () => {
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
    render(<RuntimeSurfaceHUD />);
    expect(screen.getByText('Scanning surface...')).toBeInTheDocument();
  });

  it('renders signals on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        signals: [
          { id: 'sig_12345678', type: 'test_event', payload: { foo: 'bar' } }
        ],
      }),
    });

    render(<RuntimeSurfaceHUD />);
    
    await waitFor(() => {
      expect(screen.getByText('test_event')).toBeInTheDocument();
      expect(screen.getByText(/foo/)).toBeInTheDocument();
    });
  });

  it('submits a new signal', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ signals: [] }),
    });

    render(<RuntimeSurfaceHUD />);
    
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
          body: JSON.stringify({ payload: { type: 'custom', val: 42 } })
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
          { id: 'sig_123', type: 'test_event', payload: {} }
        ],
      }),
    });

    render(<RuntimeSurfaceHUD />);
    
    await waitFor(() => {
      expect(screen.getByText('test_event')).toBeInTheDocument();
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
