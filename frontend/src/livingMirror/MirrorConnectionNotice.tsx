import type { ExperienceMode } from './experienceMode';
import { getMirrorConnectionCopy } from './mirrorConnectionCopy';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { startMirrorClient, stopMirrorClient } from '../superbrain/lib/aiosMirror';

type MirrorConnectionNoticeProps = {
  experienceMode?: ExperienceMode;
  onOpenAuthority?: () => void;
};

export function MirrorConnectionNotice({ experienceMode = 'beginner', onOpenAuthority }: MirrorConnectionNoticeProps) {
  const mirror = useMirrorStore();
  const copy = getMirrorConnectionCopy(mirror, experienceMode);

  const retry = () => {
    stopMirrorClient();
    void startMirrorClient();
  };

  return (
    <div className={`lm-connection lm-connection--${copy.tone}`} role="status" aria-live="polite">
      <span className="lm-connection__signal" aria-hidden="true" />
      <span className="lm-connection__message">
        <strong>{copy.label}</strong>
        <span>{copy.detail}</span>
      </span>
      {experienceMode === 'expert' ? <span className="lm-connection__technical">{copy.technical}</span> : null}
      {mirror.snapshotReceivedAt ? (
        <span className="lm-connection__snapshot">Snapshot {new Date(mirror.snapshotReceivedAt).toLocaleTimeString()}</span>
      ) : null}
      {mirror.compatibility ? <span>{mirror.compatibility}</span> : null}
      {copy.canRetry ? <button type="button" onClick={retry}>Try again</button> : null}
      {mirror.approvalRequired && onOpenAuthority && experienceMode === 'expert' ? (
        <button type="button" onClick={onOpenAuthority}>Pending authority needs review</button>
      ) : null}
    </div>
  );
}
