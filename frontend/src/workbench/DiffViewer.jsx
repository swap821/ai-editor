import React, { useState, useEffect } from 'react';
import HUDPanel from '../components/HUDPanel';
import { DiffEditor } from '@monaco-editor/react';
import { Columns, AlignLeft } from 'lucide-react';
import '../superbrain/lib/monacoConfig';

export default function DiffViewer({ original, modified, filename, onClose }) {
  const [inline, setInline] = useState(false);

  const handleEditorDidMount = (editor, monaco) => {
    // Define GAGOS dark diff theme based on tokens.css
    monaco.editor.defineTheme('gagos-dark-diff', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { background: '0A0B10' },
      ],
      colors: {
        'editor.background': '#0a0b10', // var(--editor-bg)
        'editor.foreground': '#f2f3f7',
        'editorGutter.background': '#0d0e13', // var(--editor-gutter)
        'diffEditor.insertedTextBackground': '#34d3991F', // var(--diff-add) approx
        'diffEditor.removedTextBackground': '#f871711F', // var(--diff-del) approx
        'diffEditor.insertedLineBackground': '#34d3990A', 
        'diffEditor.removedLineBackground': '#f871710A',
      }
    });
    monaco.editor.setTheme('gagos-dark-diff');

    // Ctrl+Shift+D to toggle inline
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyD, () => {
      setInline(prev => !prev);
    });
  };

  const HeaderExtras = () => (
    <button
      onClick={() => setInline(!inline)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        background: 'rgba(255,255,255,0.05)',
        border: 'var(--hairline)',
        borderRadius: 'var(--radius-xs)',
        padding: '2px 8px',
        color: 'var(--text-2)',
        fontSize: 'var(--text-xs)',
        cursor: 'pointer'
      }}
      title="Toggle Inline (Ctrl+Shift+D)"
    >
      {inline ? <AlignLeft size={12} /> : <Columns size={12} />}
      {inline ? 'Inline' : 'Side-by-Side'}
    </button>
  );

  const getLanguage = (fname) => {
    if (!fname) return 'javascript';
    const ext = fname.split('.').pop().toLowerCase();
    const map = { js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript', py: 'python' };
    return map[ext] || 'plaintext';
  };

  return (
    <HUDPanel
      title={`Diff: ${filename || 'Changes'}`}
      tint="base"
      defaultPosition={{ x: 100, y: 150 }}
      defaultSize={{ width: 900, height: 500 }}
      onClose={onClose}
      headerExtras={<HeaderExtras />}
    >
      <DiffEditor
        height="100%"
        width="100%"
        language={getLanguage(filename)}
        original={original}
        modified={modified}
        onMount={handleEditorDidMount}
        options={{
          renderSideBySide: !inline,
          readOnly: true,
          minimap: { enabled: false },
          fontSize: 14,
          fontFamily: 'var(--font-mono)',
          padding: { top: 16 },
          scrollBeyondLastLine: false,
          ignoreTrimWhitespace: false,
        }}
      />
    </HUDPanel>
  );
}
