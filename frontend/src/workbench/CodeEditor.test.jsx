import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import CodeEditor from './CodeEditor';
import React from 'react';

let capturedCtrlSHandler = null;

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

// Mock Monaco Editor
vi.mock('@monaco-editor/react', () => {
  return {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    default: ({ value, onMount }) => {
      // simulate onMount to trigger setup (eslint-disable applied to component factory mock)
      // eslint-disable-next-line react-hooks/rules-of-hooks
      React.useEffect(() => {
        if (onMount) {
          const mockEditor = {
            addAction: vi.fn(),
            addCommand: vi.fn((_keybinding, handler) => {
              capturedCtrlSHandler = handler;
            }),
            getValue: () => value,
          };
          const mockMonaco = {
            editor: {
              defineTheme: vi.fn(),
              setTheme: vi.fn()
            },
            KeyMod: { CtrlCmd: 2048 },
            KeyCode: { KeyS: 49 }
          };
          onMount(mockEditor, mockMonaco);
        }
      }, []);
      return <div data-testid="mock-monaco-editor">{value}</div>;
    }
  };
});

describe('CodeEditor', () => {
  beforeEach(() => {
    capturedCtrlSHandler = null;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders editor within HUDPanel', async () => {
    const file = { name: 'test.js', content: 'const a = 1;', readonly: false };
    render(<CodeEditor file={file} onClose={vi.fn()} />);

    expect(screen.getByText('test.js')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('mock-monaco-editor')).toHaveTextContent('const a = 1;');
    });
  });

  it('Ctrl+S proposes the real edit through /api/v1/files/edit instead of console.log', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'proposed', requiresHuman: true, constraints: [] }),
    });
    globalThis.fetch = fetchMock;

    const file = { name: 'test.js', path: '/abs/path/test.js', content: 'const a = 1;' };
    render(<CodeEditor file={file} onClose={vi.fn()} />);

    await waitFor(() => expect(capturedCtrlSHandler).toBeTruthy());
    await act(async () => {
      await capturedCtrlSHandler();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/files/edit'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ path: '/abs/path/test.js', content: 'const a = 1;' }),
      })
    );
    await screen.findByText('Proposed — awaiting human approval');
  });

  it('Ctrl+S surfaces a failure honestly instead of claiming success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: 'File out of bounds' }),
    });

    const file = { name: 'test.js', path: '/abs/path/test.js', content: 'const a = 1;' };
    render(<CodeEditor file={file} onClose={vi.fn()} />);

    await waitFor(() => expect(capturedCtrlSHandler).toBeTruthy());
    await act(async () => {
      await capturedCtrlSHandler();
    });

    await screen.findByText('Propose failed: File out of bounds');
  });
});
