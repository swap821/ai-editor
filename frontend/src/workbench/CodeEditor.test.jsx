import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import CodeEditor from './CodeEditor';
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
            addCommand: vi.fn()
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
  it('renders editor within HUDPanel', async () => {
    const file = { name: 'test.js', content: 'const a = 1;', readonly: false };
    render(<CodeEditor file={file} onClose={vi.fn()} />);
    
    expect(screen.getByText('test.js')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByTestId('mock-monaco-editor')).toHaveTextContent('const a = 1;');
    });
  });
});
