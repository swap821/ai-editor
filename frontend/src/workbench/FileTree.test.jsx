import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
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

describe('FileTree', () => {
  it('renders correctly', async () => {
    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText('File Tree')).toBeInTheDocument();
    
    // Wait for the mock fetch to populate the tree
    await waitFor(() => {
      expect(screen.getByText('src')).toBeInTheDocument();
      expect(screen.getByText('docs')).toBeInTheDocument();
    });
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
});
