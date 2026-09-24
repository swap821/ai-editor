import { describeConnection, describeTaskState } from '../experience/copy';
import type { BeingPresentation } from './beingPresentation';
import type { HumanTaskState } from '../experience/humanTaskStory';

type BeingStatusProps = {
  presentation: BeingPresentation;
  taskState: HumanTaskState;
  expert?: boolean;
};

const phaseLabel: Record<BeingPresentation['phase'], string> = {
  booting: 'Waking up', ready: 'Ready', listening: 'Listening', understanding: 'Understanding', planning: 'Preparing',
  'awaiting-human': 'Waiting for you', acting: 'Working', verifying: 'Checking', learning: 'Learning', reflex: 'Using a learned routine',
  recovering: 'Recovering', degraded: 'Limited connection', stale: 'Last known state', stopped: 'Stopped',
};

export function BeingStatus({ presentation, taskState, expert = false }: BeingStatusProps) {
  const connection = describeConnection(presentation.continuityState);
  const task = describeTaskState(taskState);
  return (
    <div className={`gagos-being-status gagos-being-status--${presentation.phase}`} data-being-phase={presentation.phase} aria-live="polite">
      <span className="gagos-being-status__pulse" aria-hidden="true" />
      <span className="gagos-being-status__copy">
        <strong>{phaseLabel[presentation.phase]}</strong>
        <span>{presentation.phase === 'ready' ? connection.title : taskState === 'idle' ? connection.detail : task.detail}</span>
      </span>
      {expert ? <span className="gagos-being-status__technical">{presentation.phase} · {presentation.continuityState} · {presentation.workerCount} temporary worker{presentation.workerCount === 1 ? '' : 's'}</span> : null}
    </div>
  );
}
