import React, { useState } from 'react';
import HUDPanel from '../components/HUDPanel';
import Editor from '@monaco-editor/react';
import '../superbrain/lib/monacoConfig';

export default function CodeEditor({ file, onClose }) {
  const [content, setContent] = useState(file?.content || '');

  // Map file extension to monaco language
  const getLanguage = (filename) => {
    if (!filename) return 'javascript';
    const ext = filename.split('.').pop().toLowerCase();
    const map = {
      js: 'javascript',
      jsx: 'javascript',
      ts: 'typescript',
      tsx: 'typescript',
      py: 'python',
      json: 'json',
      css: 'css',
      html: 'html',
      sql: 'sql',
      go: 'go',
      rs: 'rust',
      c: 'c',
      cpp: 'cpp',
      md: 'markdown'
    };
    return map[ext] || 'plaintext';
  };

  const handleEditorDidMount = (editor, monaco) => {
    // Define GAGOS dark theme based on tokens.css
    monaco.editor.defineTheme('gagos-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { background: '0A0B10' },
      ],
      colors: {
        'editor.background': '#0a0b10', // var(--editor-bg)
        'editor.foreground': '#f2f3f7',
        'editor.lineHighlightBackground': '#7bf5fb0A', // var(--editor-line-highlight) approx
        'editor.selectionBackground': '#7bf5fb26', // var(--editor-selection) approx
        'editorGutter.background': '#0d0e13', // var(--editor-gutter)
      }
    });
    monaco.editor.setTheme('gagos-dark');

    // Add Command Palette Action
    editor.addAction({
      id: 'ask-gagos-refactor',
      label: 'Ask GAGOS to refactor this function',
      contextMenuGroupId: 'navigation',
      contextMenuOrder: 1.5,
      run: function(ed) {
        console.log('Asked GAGOS to refactor selection');
      }
    });

    // Auto-save on Ctrl+S
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      console.log('Auto-saved', file?.name);
      // Trigger approval gate here
    });
  };

  return (
    <HUDPanel
      title={file?.name || 'Editor'}
      tint="base"
      defaultPosition={{ x: 320, y: 100 }}
      defaultSize={{ width: 800, height: 600 }}
      onClose={onClose}
    >
      <Editor
        height="100%"
        width="100%"
        language={getLanguage(file?.name)}
        value={content}
        onChange={(val) => setContent(val)}
        onMount={handleEditorDidMount}
        options={{
          readOnly: file?.readonly || false,
          minimap: { enabled: false },
          fontSize: 14,
          fontFamily: 'var(--font-mono)',
          padding: { top: 16 },
          scrollBeyondLastLine: false,
          smoothScrolling: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          formatOnPaste: true,
        }}
      />
    </HUDPanel>
  );
}
