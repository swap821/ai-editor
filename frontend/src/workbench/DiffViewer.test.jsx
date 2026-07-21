import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DiffViewer from './DiffViewer';
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

// Mock Monaco DiffEditor
vi.mock('@monaco-editor/react', () => {
  return {
    DiffEditor: ({ original, modified, onMount }) => {
      React.useEffect(() => {
        if (onMount) {
          const mockEditor = {
            addCommand: vi.fn()
          };
          const mockMonaco = {
            editor: {
              defineTheme: vi.fn(),
              setTheme: vi.fn()
            },
            KeyMod: { CtrlCmd: 2048, Shift: 1024 },
            KeyCode: { KeyD: 34 }
          };
          onMount(mockEditor, mockMonaco);
        }
      }, []);
      return (
        <div data-testid="mock-diff-editor">
          <div>Original: {original}</div>
          <div>Modified: {modified}</div>
        </div>
      );
    }
  };
});

describe('DiffViewer', () => {
  it('renders diff editor within HUDPanel', async () => {
    render(
      <DiffViewer 
        original="old code" 
        modified="new code" 
        filename="test.js" 
        onClose={vi.fn()} 
      />
    );
    
    expect(screen.getByText('Diff: test.js')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByTestId('mock-diff-editor')).toHaveTextContent('Original: old code');
      expect(screen.getByTestId('mock-diff-editor')).toHaveTextContent('Modified: new code');
    });
  });
});
