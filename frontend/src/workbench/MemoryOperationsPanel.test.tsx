import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import MemoryOperationsPanel from './MemoryOperationsPanel';

describe('MemoryOperationsPanel', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders correctly', () => {
    render(<MemoryOperationsPanel />);
    expect(screen.getByText('Compact Context')).toBeInTheDocument();
    expect(screen.getByText('Consolidate to LTM')).toBeInTheDocument();
  });

  it('handles compact context action', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Context compacted successfully' }),
    });

    render(<MemoryOperationsPanel />);
    const btn = screen.getByText('Compact Context');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/memory/compact'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Context compacted successfully')).toBeInTheDocument();
    });
  });

  it('handles vector search', async () => {
    render(<MemoryOperationsPanel />);
    
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        results: [
          {
            id: 'memory-1',
            text: 'Memory chunk 1',
            score: 0.88,
            bm25: 0.8,
            faiss: 0.9,
            recency: 0.7,
            memory_type: 'lesson',
            verification_status: 'verified',
          }
        ]
      }),
    });

    const searchInput = screen.getByPlaceholderText('Search vector space...');
    fireEvent.change(searchInput, { target: { value: 'test' } });
    
    const searchBtn = screen.getByText('Search', { selector: 'button[type="submit"]' });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/memory/search'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ query: 'test' })
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Score: 88%')).toBeInTheDocument();
      expect(screen.getByText('Memory chunk 1')).toBeInTheDocument();
    });
  });

  it('does not turn a malformed memory envelope into no vectors found', async () => {
    render(<MemoryOperationsPanel />);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    const searchInput = screen.getByPlaceholderText('Search vector space...');
    fireEvent.change(searchInput, { target: { value: 'broken memory' } });
    fireEvent.click(screen.getByText('Search', { selector: 'button[type="submit"]' }));

    await waitFor(() => {
      expect(screen.getByText('Memory search unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No vectors found.')).not.toBeInTheDocument();
  });

  it('renders incomplete scores as unavailable instead of NaN', async () => {
    render(<MemoryOperationsPanel />);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        query: 'partial',
        results: [{ id: 'memory-2', text: 'Partial memory', score: null }],
      }),
    });

    const searchInput = screen.getByPlaceholderText('Search vector space...');
    fireEvent.change(searchInput, { target: { value: 'partial' } });
    fireEvent.click(screen.getByText('Search', { selector: 'button[type="submit"]' }));

    await waitFor(() => {
      expect(screen.getByText('Score unavailable')).toBeInTheDocument();
      expect(screen.getByText('Partial memory')).toBeInTheDocument();
    });
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it('handles fact reconciliation', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Facts reconciled' }),
    });

    render(<MemoryOperationsPanel />);
    
    const fact1 = screen.getByPlaceholderText('Fact A ID or text...');
    const fact2 = screen.getByPlaceholderText('Fact B ID or text...');
    
    fireEvent.change(fact1, { target: { value: 'Earth is flat' } });
    fireEvent.change(fact2, { target: { value: 'Earth is round' } });
    
    const recBtn = screen.getByText(/Reconcile/i, { selector: 'button' });
    fireEvent.click(recBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/memory/facts/reconcile'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ fact1: 'Earth is flat', fact2: 'Earth is round' })
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Facts reconciled')).toBeInTheDocument();
    });
  });
});
