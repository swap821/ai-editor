// Render a unified diff with +/- line colouring for the approval preview.
// Added lines are green, removed lines red, hunk headers blue; the file-header
// lines (--- / +++) stay dim so they don't read as deletions/additions.
export default function DiffView({ diff }) {
  const lines = (diff || '').split('\n');
  return (
    <pre
      data-testid="diff-view"
      style={{
        background: '#0b0c10',
        borderRadius: 9,
        padding: '9px 11px',
        margin: '0 0 11px',
        fontFamily: '"Geist Mono", monospace',
        fontSize: 11,
        lineHeight: 1.55,
        maxHeight: 220,
        overflow: 'auto',
        border: '1px solid rgba(255,255,255,0.05)',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
      }}
    >
      {lines.map((line, i) => {
        let color = 'var(--text-3)';
        if (line.startsWith('+') && !line.startsWith('+++')) color = '#7ee787';
        else if (line.startsWith('-') && !line.startsWith('---')) color = '#f87171';
        else if (line.startsWith('@@')) color = '#93c5fd';
        return (
          <div key={i} style={{ color }}>
            {line || ' '}
          </div>
        );
      })}
    </pre>
  );
}
