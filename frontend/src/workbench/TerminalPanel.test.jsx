import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import TerminalPanel from './TerminalPanel';

// Mock matchMedia for framer-motion
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

// Mock HTMLElement.scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

describe('TerminalPanel', () => {
  it('renders closed by default and opens on click', () => {
    render(<TerminalPanel />);
    const toggleBtn = screen.getByText('Terminal (Ctrl+`)');
    expect(toggleBtn).toBeInTheDocument();

    // Open terminal
    fireEvent.click(toggleBtn);
    expect(screen.getByText('gag system start')).toBeInTheDocument();
  });

  it('toggles via keyboard shortcut', () => {
    render(<TerminalPanel />);

    // Simulate Ctrl+`
    fireEvent.keyDown(window, { key: '`', ctrlKey: true });
    expect(screen.getByText('gag system start')).toBeInTheDocument();

    // Close via shortcut
    fireEvent.keyDown(window, { key: '`', ctrlKey: true });
    expect(screen.getByText('Terminal (Ctrl+`)')).toBeInTheDocument();
  });

  it('runs a typed command against the real /api/terminal endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ output: 'hello world', isError: false }),
    });
    globalThis.fetch = fetchMock;

    render(<TerminalPanel />);
    fireEvent.click(screen.getByText('Terminal (Ctrl+`)'));

    const input = screen.getByPlaceholderText('Type a command...');
    fireEvent.change(input, { target: { value: 'echo hello world' } });
    fireEvent.submit(input.closest('form'));

    await screen.findByText('hello world');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/terminal'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('echo hello world'),
      })
    );
  });
});
