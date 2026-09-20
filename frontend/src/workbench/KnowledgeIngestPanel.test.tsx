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
          {
            id: 123,
            filename: 'runbook.md',
            mime_type: 'text/markdown',
            chunk_count: 5,
            created_at: '2026-09-20T10:00:00Z',
          },
        ],
      }),
    });

    render(<KnowledgeIngestPanel />);

    await waitFor(() => {
      expect(screen.getByText('runbook.md')).toBeInTheDocument();
    });

    expect(screen.getByText('5 chunks')).toBeInTheDocument();
  });

  it('does not turn a malformed source envelope into an empty knowledge base', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    render(<KnowledgeIngestPanel />);

    await waitFor(() => {
      expect(screen.getByText('Knowledge sources unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No knowledge sources ingested yet.')).not.toBeInTheDocument();
  });

  it('submits raw text as the multipart file the backend accepts', async () => {
    // Initial load
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sources: [] }),
    });

    render(<KnowledgeIngestPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('No knowledge sources ingested yet.')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Raw Text'));
    const textArea = screen.getByPlaceholderText('Paste raw documentation or facts...');
    fireEvent.change(textArea, { target: { value: 'This is a test fact.' } });

    // Setup for multipart post
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ source_id: 8, filename: 'operator-notes.txt', chunks: 1, duplicate: false }),
    });

    // Setup for reload after post
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        sources: [{ id: 999, filename: 'operator-notes.txt', mime_type: 'text/plain', chunk_count: 1, created_at: '2026-09-20T10:00:00Z' }]
      }),
    });
    const submitBtn = screen.getByText('Ingest Data');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      const ingestCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/api/v1/knowledge/ingest'));
      expect(ingestCall).toBeTruthy();
      const [, options] = ingestCall;
      expect(options.method).toBe('POST');
      expect(options.body).toBeInstanceOf(FormData);
      expect(options.body.get('file').name).toBe('operator-notes.txt');
      expect(options.body.get('file').type).toBe('text/plain');
    });

    await waitFor(() => {
      expect(screen.getByText('operator-notes.txt')).toBeInTheDocument();
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

    expect(textArea).toBeInTheDocument();
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
        entity: 'test query',
        edges: [
          {
            subject: 'test query',
            predicate: 'supports',
            object: 'Test match content',
            depth: 1,
            confidence: 0.95,
            path_confidence: 0.9,
          },
        ],
        inference: {
          answer: 'Test match content',
          confidence: 0.95,
          chain_length: 1,
          reached_horizon: false,
        },
      }),
    });

    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText('Score: 95%')).toBeInTheDocument();
      expect(screen.getByText('Test match content')).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/knowledge/query?entity=test%20query'),
      expect.anything(),
    );
  });

  it('does not turn a malformed graph response into no matching context', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sources: [] }),
    });

    render(<KnowledgeIngestPanel />);
    const searchInput = screen.getByPlaceholderText('Query the knowledge base...');
    fireEvent.change(searchInput, { target: { value: 'broken graph' } });

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });

    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText('Knowledge graph unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No matching context found.')).not.toBeInTheDocument();
  });
});
