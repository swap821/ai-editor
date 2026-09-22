import { describeTaskState } from './copy';
import { isTerminalTaskState, type HumanTaskState } from './humanTaskStory';

type OutcomeReceiptProps = {
  state: HumanTaskState;
  detail?: string;
  onReview?: () => void;
  onRetry?: () => void;
  onUndo?: () => void;
};

export function OutcomeReceipt({ state, detail, onReview, onRetry, onUndo }: OutcomeReceiptProps) {
  if (!isTerminalTaskState(state)) return null;
  const copy = describeTaskState(state);
  const caution = ['done-unverified', 'failed', 'refused', 'stopped'].includes(state);
  return (
    <section className={`gagos-outcome-receipt gagos-outcome-receipt--${state}`} aria-label="Task result" role={caution ? 'alert' : 'status'}>
      <div className="gagos-outcome-receipt__mark" aria-hidden="true">{state === 'done-verified' ? '✓' : state === 'refused' ? '!' : '·'}</div>
      <div className="gagos-outcome-receipt__body">
        <h2>{copy.title}</h2>
        <p>{detail || copy.detail}</p>
        <div className="gagos-outcome-receipt__actions">
          {onReview ? <button type="button" onClick={onReview}>Review result</button> : null}
          {onUndo && state === 'done-verified' ? <button type="button" onClick={onUndo}>Restore previous state</button> : null}
          {onRetry && ['failed', 'refused', 'done-unverified', 'restored'].includes(state) ? <button type="button" onClick={onRetry}>Try another approach</button> : null}
        </div>
      </div>
    </section>
  );
}
