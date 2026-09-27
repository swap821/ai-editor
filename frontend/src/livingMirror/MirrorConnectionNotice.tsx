import { useEffect, useState } from 'react';
import type { ExperienceMode } from './experienceMode';
import { getMirrorConnectionCopy } from './mirrorConnectionCopy';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { startMirrorClient, stopMirrorClient } from '../superbrain/lib/aiosMirror';

const COMPACT_CONNECTION_QUERY = '(max-width: 767px)';

type MirrorConnectionNoticeProps = {
  experienceMode?: ExperienceMode;
  onOpenAuthority?: (trigger: HTMLButtonElement) => void;
};

export function MirrorConnectionNotice({ experienceMode = 'beginner', onOpenAuthority }: MirrorConnectionNoticeProps) {
  const mirror = useMirrorStore();
  const copy = getMirrorConnectionCopy(mirror, experienceMode);
  const [detailsOpen, setDetailsOpen] = useState(() => (
    typeof window === 'undefined'
    || typeof window.matchMedia !== 'function'
    || !window.matchMedia(COMPACT_CONNECTION_QUERY).matches
  ));

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;

    const query = window.matchMedia(COMPACT_CONNECTION_QUERY);
    const handleViewportChange = (event: MediaQueryListEvent) => setDetailsOpen(!event.matches);
    query.addEventListener('change', handleViewportChange);
    return () => query.removeEventListener('change', handleViewportChange);
  }, []);

  const retry = () => {
    stopMirrorClient();
    void startMirrorClient();
  };

  return (
    <div
      className={`lm-connection lm-connection--${copy.tone}`}
      data-details-open={detailsOpen ? 'true' : 'false'}
      role="status"
      aria-live="polite"
    >
      <span className="lm-connection__signal" aria-hidden="true" />
      <div className="lm-connection__message">
        <strong>{copy.label}</strong>
        <details
          className="lm-connection__details"
          open={detailsOpen}
          onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
        >
          <summary>More connection details</summary>
          <span className="lm-connection__detail-content">
            <span className="lm-connection__detail">{copy.detail}</span>
            {experienceMode === 'expert' ? <span className="lm-connection__technical">{copy.technical}</span> : null}
            {mirror.snapshotReceivedAt ? (
              <span className="lm-connection__snapshot">Snapshot {new Date(mirror.snapshotReceivedAt).toLocaleTimeString()}</span>
            ) : null}
            {mirror.compatibility ? <span>{mirror.compatibility}</span> : null}
          </span>
        </details>
      </div>
      <div className="lm-connection__actions">
        {copy.canRetry ? <button type="button" onClick={retry}>Try again</button> : null}
        {mirror.approvalRequired && onOpenAuthority && experienceMode === 'expert' ? (
          <button type="button" onClick={(event) => onOpenAuthority(event.currentTarget)}>Pending authority needs review</button>
        ) : null}
      </div>
    </div>
  );
}
