import { useRendererFallbackPresentation, rendererFallbackCopy } from './rendererFallbackPresentation';

type RendererFallbackNoticeProps = {
  visible?: boolean;
  onRetry?: () => void;
};

/**
 * Product-owned explanation for a renderer failure. Retry remains owned by the
 * managed canvas boundary so this notice cannot accidentally become an action
 * or authority surface.
 */
export function RendererFallbackNotice({ visible, onRetry }: RendererFallbackNoticeProps = {}) {
  const measuredVisible = useRendererFallbackPresentation();
  if (!(visible ?? measuredVisible)) return null;

  return <aside
    className="lm-renderer-fallback-notice"
    data-testid="renderer-fallback-notice"
    role="status"
    aria-live="polite"
    aria-atomic="true"
  >
    <strong>{rendererFallbackCopy.title}</strong>
    <span>{rendererFallbackCopy.body}</span>
    {onRetry ? (
      <button type="button" className="lm-renderer-fallback__retry" onClick={onRetry}>
        Retry visual organism
      </button>
    ) : <span>{rendererFallbackCopy.retry}</span>}
  </aside>;
}
