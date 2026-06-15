import { useState, useEffect, useCallback, useRef } from 'react';
import { Html } from '@react-three/drei';
import CodeCanvas from '../components/CodeCanvas';
import LivePreview from '../components/LivePreview';
import { ErrorBoundary } from '../components/ErrorBoundary';
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
  const [pending, setPending] = useState(null); // a YELLOW write awaiting your authorization
  // Honest workspace fetch states (W2-3): loading on the first read; a quiet OFFLINE
  // banner when loadWorkspace() can't reach the backend (it used to fail silently).
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState(null);
  const editorFlaring = useFlare(isWriteEvt);
  const previewFlaring = useFlare(isRenderEvt);

  // APPROVAL-ON-DIFF (A1 + A3): a YELLOW write that PAUSES for approval — open the
  // mind's REAL proposed file (creates) in the editor and mark it PENDING (not
  // applied) until you AUTHORIZE in the panel. On resolve, the workspace re-sync
  // below replaces it with the actual on-disk file (if approved). A web file flows
  // to the live preview for free.
  useEffect(() => {
    return subscribeCognition((e) => {
      if (!e) return;
      if (e.type === 'approval-required') {
        const p = getPendingApproval();
        if (!p || (p.kind !== 'create' && p.kind !== 'edit')) return;
        setPending(p);
        if (p.kind === 'create' && p.filepath) {
          const name = baseName(p.filepath);
          setFiles((prev) => ({ ...prev, [name]: { language: langOf(name), content: p.content || '' } }));
          setActive(name);
        }
      } else if (e.type === 'approval-resolved') {
        setPending(null);
      }
    });
  }, []);

  // TRUTHFUL CONTENT (the fix): sync the editor to the REAL training_ground
  // workspace — the mind's actual ON-DISK files — regardless of how the write
  // landed (approval, EARNED-AUTONOMY auto-write, or edit). The earned path never
  // pauses for approval, so reading the workspace is the only path-independent way
  // to show the file the mind actually wrote. Honest offline: keep current files.
  const seenRef = useRef(new Set());
  const loadWorkspace = useCallback(async () => {
    setWorkspaceLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/development/workspace`, { headers: API_HEADERS });
      if (!r.ok) {
        // No longer silent (W2-3): surface the truth with the status code. A 5xx is
        // a real backend error; any other not-ok is a link/route problem. Keep the
        // current files either way — never fake content.
        setWorkspaceError(r.status >= 500 ? `Backend error ${r.status}` : `Workspace fetch failed (${r.status})`);
        return;
      }
      const data = await r.json();
      const list = Array.isArray(data.files) ? data.files : [];
      // Reaching here means the link is healthy — clear any prior offline banner.
      setWorkspaceError(null);
      if (!list.length) return; // empty workspace — keep the welcome files (not an error)
      const next = {};
      for (const f of list) next[f.path] = { language: langOf(f.path), content: f.content || '' };
      const newest = list[0].path; // most-recent write
      const isNewFile = !seenRef.current.has(newest);
      seenRef.current = new Set(Object.keys(next));
      setFiles(next);
      // Jump to a FRESHLY-written file; otherwise keep the operator's current tab.
      setActive((cur) => (isNewFile ? newest : cur && cur in next ? cur : newest));
    } catch (err) {
      // Backend unreachable — keep current files, never fake content, but no longer
      // SILENT: a quiet offline banner tells the operator the link is down (W2-3/W2-5).
      setWorkspaceError(`Workspace offline — ${err?.message || 'AI-OS unreachable'}`);
    } finally {
      setWorkspaceLoading(false);
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
      {/* PORT 01 — EDITOR, at the left nerve port. The boundary lives INSIDE
          <Html> (which portals to the DOM), so it's a valid DOM boundary that
          isolates an editor-panel render fault from the rest of the forge — it is
          never placed between the canvas and <Html> (that would break R3F). */}
      <Html position={PORT_EDITOR} zIndexRange={[100, 0]} style={{ pointerEvents: 'none' }}>
        <ErrorBoundary name="ForgePorts">
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
                aria-label="Refresh workspace files"
              >
                <span aria-hidden="true">⟳</span>
              </button>
              <span className="forge-link" />
            </div>
            {/* Honest workspace states (W2-3): a loading line on the first read, and a
                quiet OFFLINE/error banner when loadWorkspace() can't reach the backend
                (it used to fail silently). aria-live so AT announces the link drop. */}
            {workspaceLoading && !workspaceError && (
              <div className="forge-loading" role="status">
                Loading workspace…
              </div>
            )}
            {workspaceError && (
              <div className="forge-error" role="status" aria-live="polite">
                ⚠ {workspaceError}
              </div>
            )}
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
            {pending && pending.filepath && (
              <div className="forge-pending" title={pending.filepath}>
                ⏳ PENDING · {baseName(pending.filepath)} — not applied yet. Authorize in the panel.
              </div>
            )}
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
        </ErrorBoundary>
      </Html>

      {/* PORT 02 — PREVIEW, at the right nerve port (boundary inside <Html>, as above) */}
      <Html position={PORT_PREVIEW} zIndexRange={[100, 0]} style={{ pointerEvents: 'none' }}>
        <ErrorBoundary name="ForgePorts">
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
        </ErrorBoundary>
      </Html>
    </>
  );
}
