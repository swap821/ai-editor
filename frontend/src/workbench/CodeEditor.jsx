import React, { useState, useRef } from 'react';
import HUDPanel from '../components/HUDPanel';
import Editor from '@monaco-editor/react';
import '../superbrain/lib/monacoConfig';
import { API_BASE, API_HEADERS } from '../config';

async function proposeFileEdit(path, content) {
  const response = await fetch(`${API_BASE}/api/v1/files/edit`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify({ path, content }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}

export default function CodeEditor({ file, onClose }) {
  const [content, setContent] = useState(file?.content || '');
  const [saveStatus, setSaveStatus] = useState('');
  // Ctrl+S is registered once on mount via editor.addCommand; a React-state
  // closure would go stale, so track saving state in a ref the handler reads
  // live, and pull the live buffer via editor.getValue() (not React state).
  const savingRef = useRef(false);

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

    // Ctrl+S: propose the edit through the real, gated /api/v1/files/edit
    // endpoint (scope + frozen-core checked server-side). This is a PROPOSAL,
    // not a direct write -- the endpoint itself doesn't write to disk yet
    // (still requires the human-approval gate), so the UI must say
    // "proposed", never "saved", to stay honest about what happened.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, async () => {
      if (!file?.path || savingRef.current) return;
      savingRef.current = true;
      setSaveStatus('Proposing edit...');
      try {
        const result = await proposeFileEdit(file.path, editor.getValue());
        setSaveStatus(
          result.requiresHuman
            ? 'Proposed — awaiting human approval'
            : 'Proposed'
        );
      } catch (err) {
        setSaveStatus(`Propose failed: ${err.message}`);
      } finally {
        savingRef.current = false;
      }
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
      {saveStatus && (
        <div
          style={{
            padding: '4px 12px',
            fontSize: 'var(--text-xs)',
            color: saveStatus.startsWith('Propose failed') ? 'var(--danger, #f87171)' : 'var(--text-2)',
            borderBottom: 'var(--hairline)',
          }}
        >
          {saveStatus}
        </div>
      )}
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
