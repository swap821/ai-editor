import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import FileTree from './FileTree';
import React from 'react';

// Mock matchMedia for framer-motion in HUDPanel
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

const ROOT_LEVEL = [
  { name: 'src', path: '/src', type: 'directory', status: 'normal', children: [] },
  { name: 'docs', path: '/docs', type: 'directory', status: 'normal', children: [] },
];
const SRC_CHILDREN = [
  { name: 'main.jsx', path: '/src/main.jsx', type: 'file', status: 'approved' },
  { name: 'App.jsx', path: '/src/App.jsx', type: 'file', status: 'editing' },
];
const DOCS_CHILDREN = [
  { name: 'architecture.md', path: '/docs/architecture.md', type: 'file', status: 'verifying' },
  { name: 'README.md', path: '/docs/README.md', type: 'file', status: 'failed' },
];

function jsonResponse(body) {
  return { ok: true, json: async () => body };
}

describe('FileTree', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn((url) => {
      const u = String(url);
      if (u.includes('root=%2Fsrc')) return Promise.resolve(jsonResponse(SRC_CHILDREN));
      if (u.includes('root=%2Fdocs')) return Promise.resolve(jsonResponse(DOCS_CHILDREN));
      return Promise.resolve(jsonResponse(ROOT_LEVEL));
    });
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the real tree from the backend and renders it', async () => {
    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText('File Tree')).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/files/tree'),
        expect.objectContaining({ credentials: 'include' })
      );
      expect(screen.getByText('src')).toBeInTheDocument();
      expect(screen.getByText('docs')).toBeInTheDocument();
    });
  });

  it('lazily loads and renders real children of auto-expanded root directories', async () => {
    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('main.jsx')).toBeInTheDocument();
      expect(screen.getByText('README.md')).toBeInTheDocument();
    });

    // Root-level fetch + one lazy fetch per auto-expanded directory.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('filters nodes based on search query', async () => {
    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('main.jsx')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search files...');
    fireEvent.change(searchInput, { target: { value: 'README' } });

    // main.jsx should disappear, README.md should still be there
    expect(screen.queryByText('main.jsx')).not.toBeInTheDocument();
    expect(screen.getByText('README.md')).toBeInTheDocument();
  });

  it('surfaces an error state when the backend is unreachable', async () => {
    fetchMock.mockImplementation(() => Promise.resolve({ ok: false, status: 500, json: async () => ({}) }));

    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('File tree offline')).toBeInTheDocument();
    });
  });
});
