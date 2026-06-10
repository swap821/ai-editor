import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AlignmentPanel from './AlignmentPanel';

const FRAME = {
  goal: 'Implement the alignment panel',
  intent: 'execute',
  desired_outcome: 'The operator can inspect what the system understood',
  constraints: ['Keep approvals unchanged'],
  assumptions: ['The panel is read-only in this slice'],
  unknowns: ['Preferred correction workflow'],
  decisions: ['Expose the validated frame over SSE'],
  confidence: 0.91,
  next_action: 'Render the frame below the AI Agent header',
  communication: {
    mode: 'direct',
    ambiguity_action: 'state_assumptions',
    reasons: ['unverified_assumptions', 'unresolved_unknowns'],
    clarifying_question: '',
  },
};

describe('AlignmentPanel', () => {
  it('shows the goal, intent, confidence, and next action at a glance', () => {
    render(<AlignmentPanel frame={FRAME} />);

    expect(screen.getByRole('region', { name: /shared understanding/i })).toBeInTheDocument();
    expect(screen.getByText('Implement the alignment panel')).toBeInTheDocument();
    expect(screen.getByText('execute')).toBeInTheDocument();
    expect(screen.getByText('direct mode')).toBeInTheDocument();
    expect(screen.getByText('91% interpretation')).toBeInTheDocument();
    expect(screen.getByText(/Render the frame below/)).toBeInTheDocument();
    expect(screen.getByText(/Ambiguity policy: state assumptions/i)).toBeInTheDocument();
  });

  it('expands inspectable details while labeling the frame advisory', () => {
    render(<AlignmentPanel frame={FRAME} />);
    fireEvent.click(screen.getByRole('button', { name: /inspect details/i }));

    expect(screen.getByText('Keep approvals unchanged')).toBeInTheDocument();
    expect(screen.getByText('Preferred correction workflow')).toBeInTheDocument();
    expect(screen.getByText('unverified assumptions')).toBeInTheDocument();
    expect(screen.getByText(/not approval or verified evidence/i)).toBeInTheDocument();
  });

  it('submits only user-changed interpretation fields', async () => {
    const onCorrect = vi.fn().mockResolvedValue(undefined);
    render(<AlignmentPanel frame={FRAME} onCorrect={onCorrect} />);

    fireEvent.click(screen.getByRole('button', { name: /correct understanding/i }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Goal' }), {
      target: { value: 'Review the alignment panel' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save correction/i }));

    await waitFor(() => expect(onCorrect).toHaveBeenCalledWith({
      goal: 'Review the alignment panel',
    }));
    expect(screen.queryByRole('textbox', { name: 'Goal' })).not.toBeInTheDocument();
  });

  it('shows correction lifecycle and can clear an active correction', async () => {
    const onClearCorrection = vi.fn().mockResolvedValue(undefined);
    const corrected = {
      ...FRAME,
      correction: { active: true, revision: 4, corrected_fields: ['goal'], source: 'user' },
    };
    render(
      <AlignmentPanel
        frame={corrected}
        correctionHistory={[{ revision: 4, status: 'active', corrected_fields: ['goal'] }]}
        onCorrect={vi.fn()}
        onClearCorrection={onClearCorrection}
      />,
    );

    expect(screen.getByText(/user corrected/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /inspect details/i }));
    expect(screen.getByText(/Revision 4: active/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /correct understanding/i }));
    fireEvent.click(screen.getByRole('button', { name: /clear active correction/i }));

    await waitFor(() => expect(onClearCorrection).toHaveBeenCalledTimes(1));
  });

  it('records explicit human alignment feedback', async () => {
    const onFeedback = vi.fn().mockResolvedValue(undefined);
    render(<AlignmentPanel frame={FRAME} onFeedback={onFeedback} />);
    fireEvent.click(screen.getByRole('button', { name: /inspect details/i }));

    fireEvent.click(screen.getByRole('button', { name: /wrong goal/i }));

    await waitFor(() => expect(onFeedback).toHaveBeenCalledWith({
      outcome: 'misaligned',
      issues: ['wrong_goal'],
    }));
    expect(screen.getByRole('status')).toHaveTextContent(/feedback recorded/i);
  });
});
