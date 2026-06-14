import { useMemo, useState } from 'react';

/* ─── PreviewFrame ────────────────────────────────────────────────────────
   Owns its loading state. Mounted with key={srcDoc} by the parent, so every
   document change remounts it — resetting loading=true — and the iframe's
   onLoad clears it. No refs/effects, no setState-in-render.                  */
function PreviewFrame({ srcDoc }) {
  const [loading, setLoading] = useState(true);
  return (
    <div style={{ width: '100%', height: '100%', background: '#fff', position: 'relative' }}>
      {loading && (
        <div aria-hidden="true" style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, overflow: 'hidden', zIndex: 2 }}>
          <div style={{
            width: '40%', height: '100%',
            background: 'linear-gradient(90deg, transparent, #6366f1, transparent)',
            animation: 'previewBar 0.9s ease-in-out infinite',
          }}/>
        </div>
      )}
      <iframe
        srcDoc={srcDoc}
        title="Live Preview"
        sandbox="allow-scripts"
        onLoad={() => setLoading(false)}
        style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
      />
      <style>{`
        @keyframes previewBar {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  );
}

/* ─── LivePreview ─────────────────────────────────────────────────────────
   Renders the user's html/css/js in a sandboxed iframe, with an empty state
   and a runtime-error overlay for the user's own script.                    */
export default function LivePreview({ files }) {
  const css  = files?.['style.css']?.content  || '';
  const html = files?.['index.html']?.content || '';
  const js   = files?.['app.js']?.content     || '';

  // Consider the preview "empty" only when there is no markup and no script.
  const isEmpty = useMemo(
    () => html.trim().length === 0 && js.trim().length === 0,
    [html, js]
  );

  const srcDoc = useMemo(() => `
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="color-scheme" content="light dark">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'">
        <style>
          body {
            margin: 0; min-height: 100vh;
            display: flex; justify-content: center; align-items: center;
            background-color: #f9fafb;
            font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
          }
          ::-webkit-scrollbar { width: 8px; height: 8px; }
          ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
          ${css}
        </style>
      </head>
      <body>
        ${html}
        <script>
          try { ${js} } catch (e) {
            const error = document.createElement('pre');
            error.style.cssText =
              'position:fixed;bottom:0;left:0;right:0;margin:0;padding:10px 14px;' +
              'background:#fef2f2;color:#b91c1c;font:12px/1.5 ui-monospace,monospace;' +
              'border-top:1px solid #fecaca;white-space:pre-wrap;';
            error.textContent = 'Preview error: ' + String(e?.message || e);
            document.body.appendChild(error);
          }
        </script>
      </body>
    </html>
  `, [css, html, js]);

  if (isEmpty) {
    return (
      <div
        role="status"
        style={{
          width: '100%', height: '100%',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 14,
          /* Dark-glass idle state so the preview reads as the SAME OS as the dark
             editor (operator's panel-consistency note); a real rendered page
             still shows on its own light background. Light text for contrast. */
          background: '#0a0d15', color: 'rgba(180, 190, 210, 0.78)',
          padding: 24, textAlign: 'center',
        }}
      >
        <div style={{
          width: 56, height: 56, borderRadius: 16,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          /* One-accent: cyan tint (was off-canon indigo), faint glass chip. */
          background: 'linear-gradient(135deg, rgba(92,225,230,0.12), rgba(92,225,230,0.03))',
          border: '1px solid rgba(120, 160, 180, 0.22)',
        }}>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 6h16M4 12h10M4 18h7" stroke="rgba(150,200,215,0.8)" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'rgba(232, 238, 250, 0.92)' }}>Nothing to preview yet</div>
        <div style={{ fontSize: 11.5, maxWidth: 220, lineHeight: 1.6 }}>
          Ask the AI to build something, or start editing <code style={{ fontFamily: 'ui-monospace, monospace', color: '#5ce1e6' }}>index.html</code>.
        </div>
      </div>
    );
  }

  return <PreviewFrame key={srcDoc} srcDoc={srcDoc} />;
}
