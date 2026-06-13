import { useState, useEffect } from 'react';
import { Html } from '@react-three/drei';
import CodeCanvas from '../components/CodeCanvas';
import LivePreview from '../components/LivePreview';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';

/* ─── ForgePorts ─────────────────────────────────────────────────────────────
   The work surfaces mounted AS the brain's tools — in-scene <Html> panels placed
   at the EXACT canon nerve ports so the real, unchanged 3D nerves plug straight
   into them (the editor IS the left console at x=-4.8; the preview IS the right
   console at x=+4.8). Non-`transform` projection-pinned + inner
   translate(-50%,-100%) — byte-for-byte the canon anchor (SuperbrainHUD.tsx:1046).
   Each port FLARES on the matching real cognition-bus event (the same stream that
   surges the nerve), so a thought races down the cable and lands on the surface it
   changed. This renders INSIDE the one canvas (passed as WorkspaceCanvas children).
   ──────────────────────────────────────────────────────────────────────────── */

// Canon nerve port world-points (NervousSystem.tsx:292,307 / SuperbrainHUD.tsx:1046,1097).
const PORT_EDITOR = [-4.8, -1.7, 0];
const PORT_PREVIEW = [4.8, -1.5, 0];

const DEFAULT_FILES = {
  'index.html': {
    language: 'html',
    content: '<div class="hero">\n  <h1>Wired into the mind</h1>\n  <p>The brain controls this through its nerve.</p>\n</div>',
  },
  'style.css': {
    language: 'css',
    content:
      '.hero {\n  font-family: system-ui, sans-serif;\n  text-align: center;\n  margin-top: 14vh;\n  color: #1e293b;\n}\n.hero h1 { font-size: 1.7rem; margin: 0 0 8px; }\n.hero p { color: #64748b; margin: 0; }',
  },
  'app.js': { language: 'javascript', content: '// runs live in the sandboxed preview port\nconsole.log("forge online");' },
};

// Which real bus events light which port (the nerve surges on the same events).
const isWriteEvt = (e) => e.type === 'agent-dispatch' || /WRITE|EDIT|CREATE|CODE|SWARM|ROLE/.test(String(e.label || ''));
const isRenderEvt = (e) => e.type === 'knowledge-acquired' || /VERIF|SYNTH|MASTER|RENDER/.test(String(e.label || ''));

function useFlare(match) {
  const [flaring, setFlaring] = useState(false);
  useEffect(() => {
    let t;
    const unsub = subscribeCognition((e) => {
      if (e && e.type !== 'telemetry' && match(e)) {
        setFlaring(true);
        clearTimeout(t);
        t = setTimeout(() => setFlaring(false), 780);
      }
    });
    return () => {
      unsub();
      clearTimeout(t);
    };
  }, [match]);
  return flaring;
}

export default function ForgePorts() {
  const [files, setFiles] = useState(DEFAULT_FILES);
  const [active, setActive] = useState('index.html');
  const editorFlaring = useFlare(isWriteEvt);
  const previewFlaring = useFlare(isRenderEvt);
  const current = files[active];

  return (
    <>
      {/* PORT 01 — EDITOR, at the left nerve port */}
      <Html position={PORT_EDITOR} zIndexRange={[100, 0]} style={{ pointerEvents: 'none' }}>
        <div className="forge-anchor">
          <div className={`forge-port forge-editor${editorFlaring ? ' is-flaring' : ''}`}>
            <div className="forge-head">
              <span className="forge-id">PORT 01</span>
              <span className="forge-name">EDITOR</span>
              <span className="forge-link" />
            </div>
            <div className="forge-tabs">
              {Object.keys(files).map((name) => (
                <button
                  key={name}
                  className={`forge-tab${name === active ? ' is-active' : ''}`}
                  onClick={() => setActive(name)}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="forge-canvas">
              <CodeCanvas
                code={current.content}
                language={current.language}
                onChange={(code) =>
                  setFiles((prev) => ({ ...prev, [active]: { ...prev[active], content: code ?? '' } }))
                }
              />
            </div>
            <span className="forge-socket" aria-hidden="true" />
          </div>
        </div>
      </Html>

      {/* PORT 02 — PREVIEW, at the right nerve port */}
      <Html position={PORT_PREVIEW} zIndexRange={[100, 0]} style={{ pointerEvents: 'none' }}>
        <div className="forge-anchor">
          <div className={`forge-port forge-preview${previewFlaring ? ' is-flaring' : ''}`}>
            <div className="forge-head">
              <span className="forge-id">PORT 02</span>
              <span className="forge-name">PREVIEW</span>
              <span className="forge-link" />
            </div>
            <div className="forge-canvas forge-canvas--light">
              <LivePreview files={files} />
            </div>
            <span className="forge-socket" aria-hidden="true" />
          </div>
        </div>
      </Html>
    </>
  );
}
