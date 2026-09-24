import { useState } from 'react';
import type { Receipt, ReceiptAction } from './receipts';

type ReceiptCardProps = {
  receipt: Receipt;
  onReview?: () => void;
  onCheck?: () => void;
  onDiscard?: () => void;
  onPrimary?: () => void;
  onUndo?: () => void;
};

export function ReceiptCard({ receipt, onReview, onCheck, onDiscard, onPrimary, onUndo }: ReceiptCardProps) {
  const [explanationOpen, setExplanationOpen] = useState(false);
  const isReview = (action: ReceiptAction) => action === 'Review' || action === 'See changes' || action === 'See what failed';
  const isCheck = (action: ReceiptAction) => action === 'Run a check';
  const isDiscard = (action: ReceiptAction) => action === 'Discard';
  const isPrimary = (action: ReceiptAction) => action === 'Choose a safer option' || action === 'Try another approach';
  const isExplanation = (action: ReceiptAction) => action === 'Explain' || action === 'Why verified';

  return (
    <section className={`gagos-receipt gagos-receipt--${receipt.kind}`} role="status" aria-label={receipt.title}>
      <div className="gagos-receipt__heading">
        <strong>{receipt.title}</strong>
        <span className="gagos-receipt__target">{receipt.target}</span>
      </div>
      <p>{receipt.message}</p>
      <div className="gagos-receipt__actions" aria-label="Receipt actions">
        {receipt.actions.map((action) => {
          if (isExplanation(action)) {
            return (
              <button key={action} type="button" onClick={() => setExplanationOpen((open) => !open)} aria-expanded={explanationOpen}>
                {action}
              </button>
            );
          }
          if (isReview(action) && onReview) {
            return <button key={action} type="button" onClick={onReview}>{action}</button>;
          }
          if (isCheck(action) && onCheck) {
            return <button key={action} type="button" onClick={onCheck}>{action}</button>;
          }
          if (isDiscard(action) && onDiscard) {
            return <button key={action} type="button" onClick={onDiscard}>{action}</button>;
          }
          if (isPrimary(action) && onPrimary) {
            return <button key={action} type="button" onClick={onPrimary}>{action}</button>;
          }
          if (action === 'Undo' && onUndo) {
            return <button key={action} type="button" onClick={onUndo}>{action}</button>;
          }
          return null;
        })}
      </div>
      {explanationOpen ? (
        <p className="gagos-receipt__explanation">
          {receipt.kind === 'verified-success'
            ? 'This result is marked verified because a real verifier result passed. The receipt does not grant permission or change the underlying authority record.'
            : 'This receipt reports only the evidence currently available. A completed action is not presented as verified until a real verifier result arrives.'}
        </p>
      ) : null}
    </section>
  );
}
