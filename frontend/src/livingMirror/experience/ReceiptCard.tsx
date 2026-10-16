import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Receipt, ReceiptAction } from './receipts';

type ReceiptCardProps = {
  receipt: Receipt;
  onReview?: () => void;
  onCheck?: () => void;
  onDiscard?: () => void;
  onPrimary?: () => void;
  onUndo?: () => void;
  /** Presentation-only mount point in the matching selected artifact reader. */
  host?: HTMLElement | null;
  onRootChange?: (element: HTMLElement | null) => void;
};

export function ReceiptCard({ receipt, onReview, onCheck, onDiscard, onPrimary, onUndo, host = null, onRootChange }: ReceiptCardProps) {
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [readerState, setReaderState] = useState<{ receipt: Receipt; open: boolean } | null>(null);
  const critical = receipt.kind === 'failure' || receipt.kind === 'failure-rollback' || receipt.kind === 'refusal';
  const sameArtifact = !!receipt.targetTabId && receipt.targetTabId === readerState?.receipt.targetTabId;
  const readerOpen = readerState?.receipt === receipt ? readerState.open : critical || (sameArtifact && !!readerState?.open);
  const cardRef = useRef<HTMLElement | null>(null);
  const bindCard = useCallback((element: HTMLElement | null) => {
    cardRef.current = element;
    onRootChange?.(element);
  }, [onRootChange]);
  useLayoutEffect(() => {
    const reader = host?.closest<HTMLElement>('.lm-surface__body');
    const card = cardRef.current;
    if (!reader || !card) return;
    let disposed = false;
    const measure = () => {
      if (disposed) return;
      const paint = getComputedStyle(reader);
      const height = reader.clientHeight - parseFloat(paint.paddingTop) - parseFloat(paint.paddingBottom);
      if (Number.isFinite(height) && height > 0) card.style.maxHeight = `${Math.floor(height)}px`;
      else card.style.removeProperty('max-height');
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    observer?.observe(reader);
    window.addEventListener('resize', measure);
    return () => { disposed = true; observer?.disconnect(); window.removeEventListener('resize', measure); card.style.removeProperty('max-height'); };
  }, [host]);
  const isReview = (action: ReceiptAction) => action === 'Review' || action === 'See changes' || action === 'See what failed';
  const isCheck = (action: ReceiptAction) => action === 'Run a check';
  const isDiscard = (action: ReceiptAction) => action === 'Discard';
  const isPrimary = (action: ReceiptAction) => action === 'Choose a safer option' || action === 'Try another approach';
  const isExplanation = (action: ReceiptAction) => action === 'Explain' || action === 'Why verified';

  const content = <>
      {!host && <div className="gagos-receipt__heading">
        <strong>{receipt.title}</strong>
        <span className="gagos-receipt__target">{receipt.target}</span>
      </div>}
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
  </>;
  const card = <section ref={bindCard} className={`gagos-receipt gagos-receipt--${receipt.kind}`} role="status" aria-label={receipt.title}>
    {host ? <details open={readerOpen} onToggle={(event) => setReaderState({ receipt, open: event.currentTarget.open })}>
      <summary className="gagos-receipt__reader-summary" aria-label={`Receipt details: ${receipt.title}`}>
        <strong>{receipt.kind === 'verified-success' ? `${receipt.title} · verified` : receipt.title}</strong>
        <span>Details</span>
      </summary>
      <div className="gagos-receipt__reader-detail">{content}</div>
    </details> : content}
  </section>;
  // This component owns expansion state outside the portal. Returning to
  // Conversation must not reset an explanation or duplicate action owners.
  return host ? createPortal(card, host) : card;
}
