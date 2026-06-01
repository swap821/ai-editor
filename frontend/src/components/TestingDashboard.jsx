import { useState } from 'react';
import { Send, Globe, Code, Clock, Activity, CheckCircle2, XCircle } from "lucide-react";

const METHOD_COLOR = {
  GET:    '#34d399',
  POST:   '#fbbf24',
  PUT:    '#60a5fa',
  PATCH:  '#a78bfa',
  DELETE: '#f87171',
};

export default function TestingDashboard() {
  const [url, setUrl] = useState('https://jsonplaceholder.typicode.com/posts');
  const [method, setMethod] = useState('GET');
  const [reqBody, setReqBody] = useState('{\n  "title": "foo",\n  "body": "bar",\n  "userId": 1\n}');

  const [response, setResponse] = useState(null);
  const [status, setStatus] = useState(null);
  const [time, setTime] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reqTab, setReqTab] = useState('body');

  const hasBody = ['POST', 'PUT', 'PATCH'].includes(method);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setStatus(null);
    setTime(null);
    setResponse(null);

    const startTime = performance.now();
    try {
      const options = { method };
      if (hasBody) {
        options.headers = { 'Content-Type': 'application/json' };
        try {
          JSON.parse(reqBody);
          options.body = reqBody;
        } catch {
          throw new Error("Invalid JSON in Request Body");
        }
      }

      const res = await fetch(url, options);
      const endTime = performance.now();

      setStatus({ code: res.status, text: res.statusText, ok: res.ok });
      setTime(Math.round(endTime - startTime));

      const contentType = res.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        const data = await res.json();
        setResponse(JSON.stringify(data, null, 2));
      } else {
        setResponse(await res.text());
      }
    } catch (error) {
      setResponse(`Error: ${error.message}\n\nNote: Browsers block some requests due to CORS policies. Start with public APIs.`);
      setStatus({ code: 0, text: 'Failed', ok: false });
    }
    setLoading(false);
  };

  const methodColor = METHOD_COLOR[method] || 'var(--text-1)';

  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      background: 'var(--surface-0)', color: 'var(--text-2)',
      fontFamily: 'var(--font-sans)',
    }}>
      {/* Title bar */}
      <div style={{
        padding: '8px 16px', flexShrink: 0,
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 8,
        background: 'var(--surface-1)',
      }}>
        <Globe size={13} style={{ color: 'var(--info)' }} />
        <span style={{
          fontSize: 'var(--text-xs)', fontWeight: 700,
          letterSpacing: 'var(--tracking-wide)', textTransform: 'uppercase',
          color: 'var(--text-2)',
        }}>
          API Workspace
        </span>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 14, gap: 12, overflow: 'hidden' }}>
        {/* Request bar */}
        <form onSubmit={handleSend} style={{ display: 'flex', gap: 8, flexShrink: 0, height: 36 }}>
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            aria-label="HTTP method"
            style={{
              width: 96, padding: '0 10px', borderRadius: 'var(--radius-md)',
              background: 'var(--surface-3)', border: '1px solid var(--border)',
              color: methodColor, fontWeight: 700, fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)', cursor: 'pointer', outline: 'none',
            }}
          >
            {['GET', 'POST', 'PUT', 'DELETE'].map(m => <option key={m} value={m}>{m}</option>)}
          </select>

          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.example.com/endpoint"
            aria-label="Request URL"
            style={{
              flex: 1, padding: '0 12px', borderRadius: 'var(--radius-md)',
              background: 'var(--surface-3)', border: '1px solid var(--border)',
              color: 'var(--text-1)', fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)', outline: 'none',
              transition: 'border-color var(--dur-base) var(--ease-snappy)',
            }}
            onFocus={e => { e.target.style.borderColor = 'var(--border-accent)'; }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)'; }}
          />

          <button
            type="submit"
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', gap: 7, padding: '0 18px',
              borderRadius: 'var(--radius-md)', border: 'none',
              background: 'var(--accent)', color: 'var(--text-on-accent)',
              fontSize: 'var(--text-xs)', fontWeight: 600,
              opacity: loading ? 0.6 : 1, cursor: loading ? 'wait' : 'pointer',
              boxShadow: 'var(--glow-accent)',
              transition: 'transform var(--dur-fast) var(--ease-spring), opacity var(--dur-base)',
            }}
            onMouseEnter={e => { if (!loading) e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            {loading ? <Activity size={14} style={{ animation: 'spin 0.8s linear infinite' }} /> : <Send size={14} />}
            Send
          </button>
        </form>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden' }}>
          {/* Request config */}
          <div style={{
            display: 'flex', flexDirection: 'column', height: '38%', flexShrink: 0,
            borderRadius: 'var(--radius-lg)', overflow: 'hidden',
            background: 'var(--surface-1)', border: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '0 6px', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}>
              {['body', 'headers'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setReqTab(tab)}
                  style={{
                    padding: '7px 12px', background: 'none', border: 'none',
                    borderBottom: reqTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
                    color: reqTab === tab ? 'var(--text-1)' : 'var(--text-3)',
                    fontSize: 'var(--text-xs)', fontWeight: reqTab === tab ? 600 : 400,
                    textTransform: 'capitalize', transition: 'color var(--dur-fast)',
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            <div style={{ flex: 1, overflow: 'hidden' }}>
              {reqTab === 'body' ? (
                hasBody ? (
                  <textarea
                    value={reqBody}
                    onChange={(e) => setReqBody(e.target.value)}
                    spellCheck="false"
                    aria-label="Request body JSON"
                    style={{
                      width: '100%', height: '100%', resize: 'none',
                      background: 'transparent', border: 'none', outline: 'none',
                      padding: 12, color: 'var(--warn)',
                      fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
                      lineHeight: 1.6,
                    }}
                  />
                ) : (
                  <EmptyHint text={`A ${method} request has no body.`} />
                )
              ) : (
                <EmptyHint text="Content-Type is auto-generated for requests with a body." />
              )}
            </div>
          </div>

          {/* Response */}
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0,
            borderRadius: 'var(--radius-lg)', overflow: 'hidden',
            background: 'var(--surface-0)', border: '1px solid var(--border)',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)',
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                <Code size={13} /> Response
              </span>
              {status && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: status.ok ? 'var(--success)' : 'var(--danger)' }}>
                    {status.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    {status.code} {status.text}
                  </span>
                  {time != null && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--info)' }}>
                      <Clock size={12} /> {time} ms
                    </span>
                  )}
                </div>
              )}
            </div>

            <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
              {loading ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[90, 70, 80, 55, 65].map((w, i) => (
                    <div key={i} className="skeleton" style={{ height: 11, width: `${w}%` }} />
                  ))}
                </div>
              ) : response == null ? (
                <EmptyHint icon text="Send a request to see the response here." />
              ) : (
                <pre style={{
                  margin: 0, fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
                  lineHeight: 1.65, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  color: status?.ok === false ? 'var(--danger)' : 'var(--success)',
                }}>
                  {response}
                </pre>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyHint({ text, icon = false }) {
  return (
    <div style={{
      width: '100%', height: '100%',
      display: 'flex', flexDirection: 'column', gap: 10,
      alignItems: 'center', justifyContent: 'center',
      color: 'var(--text-3)', fontSize: 'var(--text-xs)',
      fontFamily: 'var(--font-mono)', textAlign: 'center', padding: 16,
    }}>
      {icon && (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ opacity: 0.4 }}>
          <path d="M4 7h16M4 12h16M4 17h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
      )}
      {text}
    </div>
  );
}
