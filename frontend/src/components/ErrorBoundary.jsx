import { Component } from 'react';

/**
 * ErrorBoundary — a production-grade React error boundary with an HONEST,
 * accessible fallback (W5-1).
 *
 * Catches errors thrown during the *render* phase of its children (not event
 * handlers, not async rejections — those are React's documented limits), shows
 * what failed, and offers a Retry button that resets the boundary so the
 * children remount. One crash in a wrapped panel no longer white-screens the
 * whole app.
 *
 * STYLING NOTE: this is the classic (`.jsx`) product tree, which styles with
 * inline CSS custom properties from src/styles/tokens.css — NOT Tailwind utility
 * classes (the Tailwind v4 @theme here exposes `danger`/`accent`/`surface2`,
 * not the hyphenated `surface-2`/`text-2` names). The fallback therefore reuses
 * the SAME existing tokens (`--surface-2`, `--surface-3`, `--danger`, `--text-2`,
 * `--text-3`, `--border`, `--accent`, `--elevation-1`) every classic panel uses,
 * so it renders correctly and introduces no new hue.
 *
 * Props:
 *   children  — the subtree to protect
 *   name      — optional context label (e.g. "AlignmentPanel") for the heading + console
 *   fallback  — optional custom fallback node (overrides the default UI)
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleRetry = this.handleRetry.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Honest, debuggable: the real error is always surfaced to the console even
    // though users see a calm fallback. Never swallow the underlying failure.
    console.error(
      `[ErrorBoundary${this.props.name ? `: ${this.props.name}` : ''}]`,
      error,
      errorInfo,
    );
  }

  handleRetry() {
    // Reset → children remount. If the fault is in a render path this clears it;
    // if it's a persistent data fault it will re-trip, which is the honest signal.
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    const { name, error } = { name: this.props.name, error: this.state.error };
    const label = name || 'Component';

    return (
      <div
        role="alert"
        aria-live="assertive"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          padding: 18,
          margin: 0,
          background: 'var(--surface-2)',
          border: '1px solid rgba(248,113,113,0.20)',
          borderRadius: 11,
          boxShadow: 'var(--elevation-1)',
          color: 'var(--text-2)',
          fontFamily: 'var(--font-sans)',
          textAlign: 'center',
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: 13,
            fontWeight: 800,
            color: 'var(--danger)',
            letterSpacing: '0.01em',
          }}
        >
          {label} Error
        </h2>
        <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5, color: 'var(--text-2)', maxWidth: 360 }}>
          Something went wrong. Try again, or reload the page.
        </p>
        {error && (
          <details style={{ width: '100%', maxWidth: 420, fontSize: 10.5 }}>
            <summary
              style={{
                cursor: 'pointer',
                color: 'var(--text-3)',
                fontFamily: 'var(--font-mono)',
                marginBottom: 6,
              }}
            >
              Details
            </summary>
            <code
              style={{
                display: 'block',
                padding: 8,
                background: 'var(--surface-3)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                fontFamily: 'var(--font-mono)',
                color: 'rgba(248,113,113,0.85)',
                overflow: 'auto',
                maxHeight: 128,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                textAlign: 'left',
              }}
            >
              {error.message || String(error)}
            </code>
          </details>
        )}
        <button
          type="button"
          onClick={this.handleRetry}
          aria-label={`Retry ${label}`}
          style={{
            marginTop: 4,
            padding: '7px 16px',
            background: 'var(--accent)',
            color: '#fff',
            border: 'none',
            borderRadius: 7,
            fontFamily: 'var(--font-sans)',
            fontSize: 11.5,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
