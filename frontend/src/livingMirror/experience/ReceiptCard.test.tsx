import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('keeps its explanation when the one receipt moves between reader and conversation hosts', async () => {
    const hostView = render(<div className="lm-surface__body" style={{ padding: '12px' }}><div data-testid="result-receipt-host" /></div>);
    const host = screen.getByTestId('result-receipt-host');
    // Only browser layout is external to jsdom; exercise the real host clamp.
    Object.defineProperty(host.parentElement, 'clientHeight', { configurable: true, value: 144 });
    const receipt = deriveReceipt({ action: 'authorize', succeeded: true, target: 'result.py', verification: 'pass' });
    const view = render(<ReceiptCard receipt={receipt} host={host} />);
    expect(host.querySelector('.gagos-receipt')).not.toBeNull();
    expect((host.querySelector('.gagos-receipt') as HTMLElement).style.maxHeight).toBe('120px');
    fireEvent.click(screen.getByLabelText('Receipt details: Done'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Why verified' })).toBeVisible());
    fireEvent.click(screen.getByRole('button', { name: 'Why verified' }));
    expect(screen.getByText(/because a real verifier result passed/)).toBeVisible();
    view.rerender(<ReceiptCard receipt={receipt} host={null} />);
    expect(host.querySelector('.gagos-receipt')).toBeNull();
    expect(screen.getByText(/because a real verifier result passed/)).toBeVisible();
    view.rerender(<ReceiptCard receipt={receipt} host={host} />);
    expect(host.querySelector('.gagos-receipt')).not.toBeNull();
    expect(screen.getAllByRole('status', { name: 'Done' })).toHaveLength(1);
    expect(screen.getByText(/because a real verifier result passed/)).toBeVisible();
    view.unmount(); hostView.unmount();
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
