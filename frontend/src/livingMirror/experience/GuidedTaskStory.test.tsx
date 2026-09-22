import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GuidedTaskStory } from './GuidedTaskStory';
import { OutcomeReceipt } from './OutcomeReceipt';

describe('guided task story surfaces', () => {
  it('uses the human story rather than internal worker vocabulary', () => {
    render(<GuidedTaskStory state="needs-permission" goal="make a useful change" />);
    expect(screen.getByRole('heading', { name: 'Your permission is needed' })).toBeInTheDocument();
    expect(screen.getByText('I am working')).toBeInTheDocument();
    expect(screen.queryByText(/worker|council|provider/i)).not.toBeInTheDocument();
  });

  it('does not render a completion receipt for a nonterminal state', () => {
    const { container } = render(<OutcomeReceipt state="working" />);
    expect(container.firstChild).toBeNull();
  });

  it('labels unverified output as unverified instead of success', () => {
    render(<OutcomeReceipt state="done-unverified" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/not verified/i);
    expect(screen.queryByText(/^Done$/)).not.toBeInTheDocument();
  });
});
