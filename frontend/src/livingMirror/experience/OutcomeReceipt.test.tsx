import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { describeTaskState } from './copy';
import { OutcomeReceipt } from './OutcomeReceipt';

describe('OutcomeReceipt', () => {
  afterEach(() => {
    cleanup();
  });

  it('shows a verified result as a status with shared copy, undo, and no retry', () => {
    const onUndo = vi.fn();
    const onRetry = vi.fn();
    const copy = describeTaskState('done-verified');

    render(<OutcomeReceipt state="done-verified" onUndo={onUndo} onRetry={onRetry} />);

    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(copy.title);
    expect(screen.getByText(copy.detail)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Restore previous state' }));
    expect(onUndo).toHaveBeenCalledTimes(1);

    expect(screen.queryByRole('button', { name: 'Try another approach' })).toBeNull();
    expect(onRetry).not.toHaveBeenCalled();
  });

  it('treats a failed result as an alert, prefers the caller detail, and offers retry only', () => {
    const onRetry = vi.fn();

    render(
      <OutcomeReceipt
        state="failed"
        detail="Build step exited with code 1"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByText('Build step exited with code 1')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Restore previous state' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Try another approach' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('renders the review button only when a review handler is supplied', () => {
    const { unmount } = render(<OutcomeReceipt state="refused" />);
    expect(screen.queryByRole('button', { name: 'Review result' })).toBeNull();
    unmount();

    const onReview = vi.fn();
    render(<OutcomeReceipt state="refused" onReview={onReview} />);

    fireEvent.click(screen.getByRole('button', { name: 'Review result' }));
    expect(onReview).toHaveBeenCalledTimes(1);
  });
});
