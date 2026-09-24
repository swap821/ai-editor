import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReceiptCard } from './ReceiptCard';
import { deriveReceipt } from './receipts';

describe('ReceiptCard', () => {
  it('exposes the verified-result explanation action instead of silently dropping it', () => {
    const receipt = deriveReceipt({
      action: 'authorize',
      succeeded: true,
      target: 'the project files',
      verification: 'pass',
    });

    render(<ReceiptCard receipt={receipt} />);

    expect(screen.getByRole('button', { name: 'Why verified' })).toBeInTheDocument();
  });

  it('routes failure inspection to the safe review path', () => {
    const onReview = vi.fn();
    const receipt = deriveReceipt({
      action: 'authorize',
      succeeded: false,
      target: 'the project files',
      verification: 'fail',
    });

    render(<ReceiptCard receipt={receipt} onReview={onReview} />);
    fireEvent.click(screen.getByRole('button', { name: 'See what failed' }));

    expect(onReview).toHaveBeenCalledOnce();
  });

  it('routes an evidence-backed Undo action to its explicit callback', () => {
    const onUndo = vi.fn();
    const receipt = deriveReceipt({
      action: 'authorize',
      succeeded: true,
      target: 'the project files',
      verification: 'pass',
      undoAvailable: true,
    });

    render(<ReceiptCard receipt={receipt} onUndo={onUndo} />);
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));

    expect(onUndo).toHaveBeenCalledOnce();
  });

  it('keeps the unverified receipt actions available without auto-running a check', () => {
    const onReview = vi.fn();
    const onCheck = vi.fn();
    const onDiscard = vi.fn();
    const receipt = deriveReceipt({
      action: 'authorize',
      succeeded: true,
      target: 'demo.py',
      verification: 'unknown',
    });

    render(<ReceiptCard receipt={receipt} onReview={onReview} onCheck={onCheck} onDiscard={onDiscard} />);
    fireEvent.click(screen.getByRole('button', { name: 'Review' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run a check' }));
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));

    expect(onReview).toHaveBeenCalledOnce();
    expect(onCheck).toHaveBeenCalledOnce();
    expect(onDiscard).toHaveBeenCalledOnce();
  });
});
