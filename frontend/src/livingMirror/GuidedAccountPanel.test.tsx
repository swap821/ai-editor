import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GuidedAccountPanel } from './GuidedAccountPanel';

const unknownStatus = { sessionActive: false, operatorId: null, measured: 'unknown' as const };
const unlinkedStatus = { sessionActive: true, operatorId: null, measured: 'measured' as const };
const linkedStatus = { sessionActive: true, operatorId: 'op-private', measured: 'measured' as const };

describe('GuidedAccountPanel', () => {
  it('keeps an unknown account measurement unknown and does not expose technical ceremony language', () => {
    render(<GuidedAccountPanel status={unknownStatus} onClose={vi.fn()} onOpenExpert={vi.fn()} />);

    expect(screen.getByRole('dialog', { name: 'Account status unavailable' })).toBeInTheDocument();
    expect(screen.getByText(/could not confirm the account connection/i)).toBeInTheDocument();
    expect(screen.queryByText(/sovereign|credential|claim sovereignty|human sovereign/i)).not.toBeInTheDocument();
  });

  it('describes measured linked and unlinked states without exposing the operator id', () => {
    const { rerender } = render(
      <GuidedAccountPanel status={linkedStatus} onClose={vi.fn()} onOpenExpert={vi.fn()} />,
    );
    expect(screen.getByRole('heading', { name: 'Account linked' })).toBeInTheDocument();
    expect(screen.queryByText('op-private')).not.toBeInTheDocument();

    rerender(<GuidedAccountPanel status={unlinkedStatus} onClose={vi.fn()} onOpenExpert={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Account not linked' })).toBeInTheDocument();
    expect(screen.getByText(/you can still ask questions/i)).toBeInTheDocument();
  });

  it('supports Escape, close, and the explicit Expert visibility handoff', () => {
    const onClose = vi.fn();
    const onOpenExpert = vi.fn();
    render(<GuidedAccountPanel status={unlinkedStatus} onClose={onClose} onOpenExpert={onOpenExpert} />);

    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(screen.getByRole('button', { name: 'Keep working' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open Expert / Mirror' }));

    expect(onClose).toHaveBeenCalledTimes(2);
    expect(onOpenExpert).toHaveBeenCalledTimes(1);
  });

  it('keeps keyboard focus inside the dialog at both Tab boundaries', () => {
    render(<GuidedAccountPanel status={unlinkedStatus} onClose={vi.fn()} onOpenExpert={vi.fn()} />);

    const close = screen.getByRole('button', { name: 'Close' });
    const keepWorking = screen.getByRole('button', { name: 'Keep working' });

    keepWorking.focus();
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(document.activeElement).toBe(close);

    close.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(keepWorking);
  });
});
