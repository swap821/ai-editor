import { useState, useEffect, useCallback, useRef } from 'react';
import { Html } from '@react-three/drei';
import CodeCanvas from '../components/CodeCanvas';
import LivePreview from '../components/LivePreview';
import { API_BASE, API_HEADERS } from '../config';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';
import { getPendingApproval } from '../superbrain/lib/aiosAdapter';

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

// Map an agent-written file onto an editor tab (truthful content).
const EXT_LANG = { html: 'html', css: 'css', js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript', json: 'json', py: 'python', md: 'markdown', sh: 'shell', txt: 'plaintext' };
const baseName = (p) => String(p).split(/[\\/]/).pop() || String(p);
const langOf = (name) => EXT_LANG[String(name).split('.').pop()?.toLowerCase()] || 'plaintext';

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

  // TRUTHFUL CONTENT (A1): when the mind proposes a create_file, open its REAL
  // proposed content as an editor tab (from the captured approval; the adapter
  // now exposes it). It sits there until you AUTHORIZE — also the A3 seed. A
  // web file (index.html/style.css/app.js) flows on to the live preview for free.
  useEffect(() => {
    return subscribeCognition((e) => {
      if (!e || e.type !== 'approval-required') return;
      const p = getPendingApproval();
      if (!p || p.kind !== 'create' || !p.filepath) return;
      const name = baseName(p.filepath);
      setFiles((prev) => ({ ...prev, [name]: { language: langOf(name), content: p.content || '' } }));
      setActive(name);
    });
  }, []);

  // TRUTHFUL CONTENT (the fix): sync the editor to the REAL training_ground
  // workspace — the mind's actual ON-DISK files — regardless of how the write
  // landed (approval, EARNED-AUTONOMY auto-write, or edit). The earned path never
  // pauses for approval, so reading the workspace is the only path-independent way
  // to show the file the mind actually wrote. Honest offline: keep current files.
  const seenRef = useRef(new Set());
  const loadWorkspace = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/v1/development/workspace`, { headers: API_HEADERS });
      if (!r.ok) return;
      const data = await r.json();
      const list = Array.isArray(data.files) ? data.files : [];
      if (!list.length) return; // empty / backend down — keep the welcome files
      const next = {};
      for (const f of list) next[f.path] = { language: langOf(f.path), content: f.content || '' };
      const newest = list[0].path; // most-recent write
      const isNewFile = !seenRef.current.has(newest);
      seenRef.current = new Set(Object.keys(next));
      setFiles(next);
      // Jump to a FRESHLY-written file; otherwise keep the operator's current tab.
      setActive((cur) => (isNewFile ? newest : cur && cur in next ? cur : newest));
    } catch {
      // backend unreachable — keep current files, never fake content
    }
  }, []);

  useEffect(() => { loadWorkspace(); }, [loadWorkspace]); // on mount
  useEffect(() => {
    let timers = [];
    const unsub = subscribeCognition((e) => {
      if (!e || e.type === 'telemetry') return;
      // A turn did something — re-read the real workspace a FEW times, because the
      // earned-autonomy event fires just BEFORE the write completes (and verify/done
      // land a bit later). Bounded bursts (not a continuous poll), reset each event,
      // so the operator's tab is never disrupted between turns.
      if (
        e.type === 'synthesis' ||
        e.type === 'knowledge-acquired' ||
        e.type === 'approval-resolved' ||
        e.type === 'agent-dispatch'
      ) {
        timers.forEach(clearTimeout);
        timers = [350, 1500, 3500].map((d) => setTimeout(loadWorkspace, d));
      }
    });
    return () => {
      unsub();
      timers.forEach(clearTimeout);
    };
  }, [loadWorkspace]);

  const current = files[active] || files[Object.keys(files)[0]] || { content: '', language: 'plaintext' };

  return (
    <>
      {/* PORT 01 — EDITOR, at the left nerve port */}
      <Html position={PORT_EDITOR} zIndexRange={[100, 0]} style={{ pointerEvents: 'none' }}>
        <div className="forge-anchor">
          <div className={`forge-port forge-editor${editorFlaring ? ' is-flaring' : ''}`}>
            <div className="forge-head">
              <span className="forge-id">PORT 01</span>
              <span className="forge-name">EDITOR</span>
              <button
                type="button"
                className="forge-sync"
                onClick={loadWorkspace}
                title="Re-read the agent's training_ground workspace"
              >
                ⟳
              </button>
              <span className="forge-link" />
            </div>
            <div className="forge-tabs">
              {Object.keys(files).map((name) => (
                <button
                  key={name}
                  className={`forge-tab${name === active ? ' is-active' : ''}`}
                  onClick={() => setActive(name)}
                  title={name}
                >
                  {baseName(name)}
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
