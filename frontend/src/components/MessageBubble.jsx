import { useState } from 'react';

/* ─── Tool metadata ─────────────────────────────────────────── */
const TOOL_META = {
  read_file:        { icon: '📄', label: 'Read file',        color: '#60a5fa' },
  read_directory:   { icon: '📁', label: 'Scan directory',   color: '#a78bfa' },
  execute_terminal: { icon: '⚡', label: 'Run command',      color: '#34d399' },
  search_internet:  { icon: '🔍', label: 'Web search',       color: '#f9a8d4' },
  create_snapshot:  { icon: '💾', label: 'Snapshot',         color: '#fbbf24' },
  rollback_workspace:{ icon: '↩', label: 'Rollback',         color: '#f87171' },
  map_knowledge:    { icon: '🕸', label: 'Map knowledge',    color: '#c084fc' },
  query_knowledge:  { icon: '🔮', label: 'Query knowledge',  color: '#818cf8' },
  reflect:          { icon: '🧠', label: 'Lesson learned',   color: '#fbbf24' },
  verify:           { icon: '✅', label: 'Verify',           color: '#22c55e' },
  plan:             { icon: '📋', label: 'Plan',             color: '#38bdf8' },
  self_analyze:     { icon: '🔬', label: 'Self-analysis',    color: '#2dd4bf' },
  edit_file:        { icon: '✏️', label: 'Edit file',        color: '#fbbf24' },
  create_file:      { icon: '🆕', label: 'Create file',      color: '#34d399' },
  earned_autonomy:  { icon: '⚡', label: 'Autonomous action', color: '#fbbf24' },
};

/* ─── Agent Step Card ───────────────────────────────────────── */
function AgentStep({ step, settled }) {
  const [expanded, setExpanded] = useState(false);
  const meta = TOOL_META[step.tool] || { icon: '🔧', label: step.tool, color: '#9ca3af' };

  if (step.type === 'tool_call') {
    const inputPreview = Object.entries(step.input || {})
      .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v).slice(0, 60) : String(v).slice(0, 60)}`)
      .join(', ');
    return (
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 8,
        padding: '6px 10px',
        borderRadius: 8,
        background: 'rgba(255,255,255,0.03)',
        border: `1px solid ${meta.color}20`,
        position: 'relative',
        animation: 'stepIn 0.28s ease-out both',
      }}>
        <span style={{ fontSize: 14, lineHeight: 1.4, flexShrink: 0, marginTop: 1 }}>{meta.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: meta.color }}>{meta.label}</span>
            {settled ? (
              // Turn is over (done / paused for approval / error): the step is
              // recorded, so show a static dot rather than a forever-spinner.
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: meta.color, opacity: 0.5,
                display: 'inline-block', flexShrink: 0,
              }} />
            ) : (
              <span style={{
                width: 12, height: 12, borderRadius: '50%',
                border: `2px solid ${meta.color}`,
                borderTopColor: 'transparent',
                animation: 'spin 0.8s linear infinite',
                display: 'inline-block', flexShrink: 0,
              }} />
            )}
          </div>
          {inputPreview && (
            <div style={{ fontSize: 10.5, color: 'var(--text-3)', marginTop: 2, fontFamily: '"Geist Mono", monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {inputPreview}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (step.type === 'tool_result') {
    return (
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 8,
        padding: '6px 10px',
        borderRadius: 8,
        background: 'rgba(52,211,153,0.04)',
        border: '1px solid rgba(52,211,153,0.12)',
        animation: 'stepIn 0.28s ease-out both',
      }}>
        <span style={{ fontSize: 12, color: '#34d399', flexShrink: 0, marginTop: 2 }}>✓</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: meta.color }}>{meta.label}</span>
            <span style={{ fontSize: 10, color: '#34d399', fontWeight: 600 }}>done</span>
            {step.output && (
              <button
                onClick={() => setExpanded(x => !x)}
                style={{
                  marginLeft: 'auto', fontSize: 9, color: 'var(--text-3)',
                  background: 'var(--surface-3)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '1px 6px', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {expanded ? 'hide' : 'output'}
              </button>
            )}
          </div>
          {expanded && step.output && (
            <pre style={{
              marginTop: 6, fontSize: 10.5, color: 'var(--text-2)',
              fontFamily: '"Geist Mono", monospace', whiteSpace: 'pre-wrap',
              wordBreak: 'break-all', background: 'var(--surface-0)',
              border: '1px solid var(--border)', borderRadius: 6,
              padding: '8px 10px', maxHeight: 140, overflowY: 'auto',
            }}>
              {step.output}
            </pre>
          )}
        </div>
      </div>
    );
  }

  if (step.type === 'tool_blocked') {
    return (
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 8,
        padding: '6px 10px', borderRadius: 8,
        background: 'rgba(248,113,113,0.06)',
        border: '1px solid rgba(248,113,113,0.2)',
        animation: 'stepIn 0.28s ease-out both',
      }}>
        <span style={{ fontSize: 12, flexShrink: 0, marginTop: 2 }}>🛡</span>
        <div>
          <span style={{ fontSize: 11, fontWeight: 600, color: '#f87171' }}>Blocked</span>
          <span style={{ fontSize: 10.5, color: 'var(--text-3)', marginLeft: 6 }}>{step.reason}</span>
        </div>
      </div>
    );
  }

  return null;
}

/* ─── Markdown: inline formatting ───────────────────────────── */
function renderInline(text, keyBase) {
  const parts = [];
  // Match **bold**, *italic*, `code`
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g;
  let last = 0, m, idx = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={`${keyBase}-t${idx++}`}>{text.slice(last, m.index)}</span>);
    const raw = m[0];
    if (raw[0] === '`') {
      parts.push(
        <code key={`${keyBase}-c${idx++}`} style={{
          fontFamily: '"Geist Mono", monospace',
          fontSize: '0.88em',
          background: 'rgba(255,255,255,0.07)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 4,
          padding: '1px 5px',
          color: '#93c5fd',
        }}>
          {raw.slice(1, -1)}
        </code>
      );
    } else if (raw.startsWith('**')) {
      parts.push(<strong key={`${keyBase}-b${idx++}`} style={{ fontWeight: 700, color: 'var(--text-1)' }}>{raw.slice(2, -2)}</strong>);
    } else {
      parts.push(<em key={`${keyBase}-i${idx++}`} style={{ fontStyle: 'italic', color: 'var(--text-2)' }}>{raw.slice(1, -1)}</em>);
    }
    last = m.index + raw.length;
  }
  if (last < text.length) parts.push(<span key={`${keyBase}-t${idx}`}>{text.slice(last)}</span>);
  return parts.length > 0 ? parts : text;
}

/* ─── Code Block ─────────────────────────────────────────────── */
function CodeBlock({ lang, code }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const langColors = {
    javascript: '#f0db4f', js: '#f0db4f', typescript: '#3178c6', ts: '#3178c6',
    html: '#e34c26', css: '#264de4', python: '#3572a5', py: '#3572a5',
    json: '#5bcefa', bash: '#89e051', sh: '#89e051', text: '#9ca3af',
  };
  const langColor = langColors[lang?.toLowerCase()] || '#9ca3af';

  return (
    <div style={{
      borderRadius: 10, overflow: 'hidden',
      border: '1px solid rgba(255,255,255,0.07)',
      background: '#0c0d12',
      margin: '8px 0',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 14px',
        background: 'rgba(255,255,255,0.03)',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}>
        <span style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em',
          textTransform: 'uppercase', color: langColor,
          fontFamily: '"Geist Mono", monospace',
        }}>
          {lang || 'code'}
        </span>
        <button
          onClick={copy}
          style={{
            fontSize: 10.5, fontWeight: 600,
            color: copied ? '#34d399' : 'var(--text-3)',
            background: 'none', border: 'none',
            cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 4,
            transition: 'color 0.2s',
            padding: '2px 4px',
          }}
        >
          {copied ? (
            <>
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2 6.5L4.5 9L10 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
              Copied
            </>
          ) : (
            <>
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.3"/><path d="M3 8H2.5A1.5 1.5 0 0 1 1 6.5V2.5A1.5 1.5 0 0 1 2.5 1H6.5A1.5 1.5 0 0 1 8 2.5V3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              Copy
            </>
          )}
        </button>
      </div>
      {/* Code */}
      <pre style={{
        margin: 0, padding: '14px 16px',
        fontFamily: '"Geist Mono", "Fira Code", "Cascadia Code", monospace',
        fontSize: 12.5, lineHeight: 1.7,
        color: '#e2e8f0',
        overflowX: 'auto',
        whiteSpace: 'pre',
      }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

/* ─── Markdown Text Block ───────────────────────────────────── */
function MarkdownText({ text }) {
  const lines = text.split('\n');
  const elements = [];
  let listBuffer = [];
  let listType = null;
  let keyIdx = 0;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    const Tag = listType === 'ordered' ? 'ol' : 'ul';
    elements.push(
      <Tag key={`list-${keyIdx++}`} style={{
        margin: '4px 0 4px 18px', padding: 0, lineHeight: 1.8,
        color: 'var(--text-1)',
      }}>
        {listBuffer.map((item, i) => (
          <li key={i} style={{ fontSize: 13, marginBottom: 2, color: 'var(--text-2)' }}>
            {renderInline(item, `li-${keyIdx}-${i}`)}
          </li>
        ))}
      </Tag>
    );
    listBuffer = [];
    listType = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Header H3
    if (/^### (.+)/.test(line)) {
      flushList();
      elements.push(<p key={keyIdx++} style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', margin: '10px 0 4px', letterSpacing: '-0.01em' }}>{renderInline(line.slice(4), `h3-${keyIdx}`)}</p>);
      continue;
    }
    // Header H2
    if (/^## (.+)/.test(line)) {
      flushList();
      elements.push(<p key={keyIdx++} style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)', margin: '12px 0 4px', borderBottom: '1px solid var(--border)', paddingBottom: 4 }}>{renderInline(line.slice(3), `h2-${keyIdx}`)}</p>);
      continue;
    }
    // Header H1
    if (/^# (.+)/.test(line)) {
      flushList();
      elements.push(<p key={keyIdx++} style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-1)', margin: '12px 0 6px' }}>{renderInline(line.slice(2), `h1-${keyIdx}`)}</p>);
      continue;
    }
    // Bullet list
    if (/^[-*+] (.+)/.test(line)) {
      if (listType === 'ordered') flushList();
      listType = 'bullet';
      listBuffer.push(line.slice(2));
      continue;
    }
    // Numbered list
    if (/^\d+\. (.+)/.test(line)) {
      if (listType === 'bullet') flushList();
      listType = 'ordered';
      listBuffer.push(line.replace(/^\d+\. /, ''));
      continue;
    }
    // Empty line
    if (!line.trim()) {
      flushList();
      elements.push(<div key={keyIdx++} style={{ height: 6 }} />);
      continue;
    }
    // Regular paragraph
    flushList();
    elements.push(
      <p key={keyIdx++} style={{ margin: '2px 0', fontSize: 13, lineHeight: 1.75, color: 'var(--text-1)' }}>
        {renderInline(line, `p-${keyIdx}`)}
      </p>
    );
  }
  flushList();
  return <>{elements}</>;
}

/* ─── Parse text → blocks (code + text) ─────────────────────── */
function parseContent(text) {
  const segments = [];
  const codeRe = /```(\w*)\r?\n?([\s\S]*?)```/g;
  let last = 0, m;
  while ((m = codeRe.exec(text)) !== null) {
    if (m.index > last) segments.push({ type: 'text', content: text.slice(last, m.index) });
    segments.push({ type: 'code', lang: m[1] || 'text', content: m[2].replace(/\n$/, '') });
    last = m.index + m[0].length;
  }
  if (last < text.length) segments.push({ type: 'text', content: text.slice(last) });
  return segments;
}

/* ─── MessageBubble ─────────────────────────────────────────── */
export default function MessageBubble({ msg }) {
  const isUser = msg.sender === 'user';

  if (isUser) {
    return (
      <div style={{
        alignSelf: 'flex-end',
        maxWidth: '85%',
        background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
        color: '#fff',
        borderRadius: '16px 16px 4px 16px',
        padding: '10px 14px',
        fontSize: 13, lineHeight: 1.65,
        wordBreak: 'break-word',
        boxShadow: '0 4px 18px rgba(59,130,246,0.28), inset 0 1px 0 rgba(255,255,255,0.14)',
        whiteSpace: 'pre-wrap',
        animation: 'messageIn 0.34s cubic-bezier(0.22,1,0.36,1) both',
      }}>
        {msg.text}
      </div>
    );
  }

  // AI message
  return (
    <div style={{ alignSelf: 'flex-start', maxWidth: '92%', display: 'flex', flexDirection: 'column', gap: 6, animation: 'messageIn 0.34s cubic-bezier(0.22,1,0.36,1) both' }}>
      {/* Agent steps */}
      {msg.steps && msg.steps.length > 0 && (
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 4,
          padding: '10px 12px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: '12px 12px 12px 4px',
        }}>
          <div style={{
            fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'var(--text-3)',
            marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: 'var(--accent)',
              boxShadow: '0 0 6px var(--accent)',
              display: 'inline-block',
              animation: msg.loading ? 'breathe 2s ease-in-out infinite' : 'none',
            }}/>
            Agent steps
          </div>
          {msg.steps.map((step, i) => (
            <AgentStep key={`${step.id}-${i}`} step={step} settled={!!msg.settled} isLast={i === msg.steps.length - 1} />
          ))}
        </div>
      )}

      {/* Text content */}
      {(msg.loading || msg.text) && (
        <div style={{
          background: 'var(--surface-3)',
          color: 'var(--text-1)',
          border: '1px solid var(--border)',
          borderRadius: msg.steps?.length > 0 ? '12px 12px 12px 4px' : '4px 16px 16px 16px',
          padding: '10px 14px',
          wordBreak: 'break-word',
          boxShadow: '0 2px 10px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.03)',
        }}>
          {msg.loading && !msg.text ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-3)' }}>
              <span style={{ display: 'inline-flex', gap: 3 }}>
                {[0, 1, 2].map(i => (
                  <span key={i} style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: 'var(--accent)',
                    animation: 'pulse 1.2s ease-in-out infinite',
                    animationDelay: `${i * 0.2}s`,
                    display: 'inline-block',
                  }}/>
                ))}
              </span>
              <span style={{ fontSize: 12 }}>Thinking…</span>
            </span>
          ) : (
            <>
              {parseContent(msg.text).map((seg, i) =>
                seg.type === 'code'
                  ? <CodeBlock key={i} lang={seg.lang} code={seg.content} />
                  : <MarkdownText key={i} text={seg.content} />
              )}
              {msg.streaming && (
                <span style={{
                  display: 'inline-block', width: 2, height: 14,
                  background: 'var(--accent)',
                  marginLeft: 2,
                  animation: 'cursor-blink 0.8s steps(2) infinite',
                  verticalAlign: 'text-bottom',
                  borderRadius: 1,
                }}/>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
