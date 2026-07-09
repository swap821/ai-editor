import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import KnowledgeIngestPanel from './KnowledgeIngestPanel';

describe('KnowledgeIngestPanel', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    fetchMock.mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<KnowledgeIngestPanel />);
    expect(screen.getByText('Loading sources...')).toBeInTheDocument();
  });

  it('renders sources on successful load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        sources: [
          { id: '123', type: 'url', url: 'https://example.com', chunks: 5 },
        ],
      }),
    });

    render(<KnowledgeIngestPanel />);
    
    await waitFor(() => {
      expect(screen.getByText(/example\.com/)).toBeInTheDocument();
    });
    
    expect(screen.getByText('5 chunks')).toBeInTheDocument();
  });

  it('submits a new URL source', async () => {
    // Initial load
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sources: [] }),
    });

    render(<KnowledgeIngestPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('No knowledge sources ingested yet.')).toBeInTheDocument();
    });

    // Setup for post
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Ingested' }),
    });

    // Setup for reload after post
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        sources: [{ id: '999', type: 'url', url: 'https://test.com', chunks: 10 }]
      }),
    });

    const input = screen.getByPlaceholderText('https://docs.example.com');
    fireEvent.change(input, { target: { value: 'https://test.com' } });
    
    const submitBtn = screen.getByText('Ingest Data');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/knowledge/ingest'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ url: 'https://test.com' })
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/test\.com/)).toBeInTheDocument();
    });
  });

  it('can switch to text ingest mode and submit', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sources: [] }),
    });

    render(<KnowledgeIngestPanel />);
    
    const textTabBtn = screen.getByText('Raw Text');
    fireEvent.click(textTabBtn);

    const textArea = screen.getByPlaceholderText('Paste raw documentation or facts...');
    expect(textArea).toBeInTheDocument();

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Ingested' }),
    });
    
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sources: [] }), // dummy reload
    });

    fireEvent.change(textArea, { target: { value: 'This is a test fact.' } });
    fireEvent.click(screen.getByText('Ingest Data'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/knowledge/ingest'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ text: 'This is a test fact.' })
        })
      );
    });
  });

  it('handles search queries', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sources: [] }),
    });

    render(<KnowledgeIngestPanel />);
    
    const searchInput = screen.getByPlaceholderText('Query the knowledge base...');
    fireEvent.change(searchInput, { target: { value: 'test query' } });
    
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        results: [
          { score: 0.95, text: 'Test match content', source_id: 'src_123' }
        ]
      }),
    });

    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText('Score: 95%')).toBeInTheDocument();
      expect(screen.getByText('Test match content')).toBeInTheDocument();
    });
  });
});
