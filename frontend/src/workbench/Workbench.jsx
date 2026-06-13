import { useState } from 'react';
import CodeCanvas from '../components/CodeCanvas';
import LivePreview from '../components/LivePreview';

/* ─── Workbench ──────────────────────────────────────────────────────────────
   The manufacturing surface — the real Monaco editor (CodeCanvas) + the real
   sandboxed LivePreview, floating as glass slabs in the same infinite space the
   superbrain voyages through. Phase 2 increment 1 is the FORM: a self-contained
   editor+preview that proves the manufacturing dock. Wiring the agent's own
   writes into these files (and sharing the unified turn/approval state) is a
   later increment — this is the workbench taking shape, not yet the agent's hands.
   ──────────────────────────────────────────────────────────────────────────── */

const DEFAULT_FILES = {
  'index.html': {
    language: 'html',
    content:
      '<div class="hero">\n  <h1>The workbench, in the superbrain</h1>\n  <p>Edit any file — the preview updates live.</p>\n</div>',
  },
  'style.css': {
    language: 'css',
    content:
      '.hero {\n  font-family: system-ui, sans-serif;\n  text-align: center;\n  margin-top: 16vh;\n  color: #1e293b;\n}\n.hero h1 { font-size: 2rem; margin: 0 0 8px; }\n.hero p { color: #64748b; margin: 0; }',
  },
  'app.js': {
    language: 'javascript',
    content: '// JavaScript runs live in the sandboxed preview.\nconsole.log("workbench online");',
  },
};

export default function Workbench() {
  const [files, setFiles] = useState(DEFAULT_FILES);
  const [active, setActive] = useState('index.html');
  const current = files[active];

  return (
    <div className="wb">
      {/* Editor slab */}
      <div className="wb-pane wb-editor">
        <div className="wb-tabs">
          {Object.keys(files).map((name) => (
            <button
              key={name}
              className={`wb-tab${name === active ? ' is-active' : ''}`}
              onClick={() => setActive(name)}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="wb-canvas">
          <CodeCanvas
            code={current.content}
            language={current.language}
            onChange={(code) =>
              setFiles((prev) => ({ ...prev, [active]: { ...prev[active], content: code ?? '' } }))
            }
          />
        </div>
      </div>

      {/* Live preview slab */}
      <div className="wb-pane wb-preview">
        <div className="wb-preview-chrome">
          <span className="wb-dot" />
          <span className="wb-dot" />
          <span className="wb-dot" />
          <div className="wb-url">preview://localhost</div>
        </div>
        <div className="wb-canvas">
          <LivePreview files={files} />
        </div>
      </div>
    </div>
  );
}
