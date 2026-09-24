import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StarterPaths } from './StarterPaths';

describe('StarterPaths', () => {
  it('offers understandable paths and only returns the selected prompt', () => {
    const onChoose = vi.fn();
    render(<StarterPaths onChoose={onChoose} />);

    expect(screen.getByRole('group', { name: 'Choose how to begin' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ask & understand/i })).toBeInTheDocument();
    expect(screen.getByText('Explain something, compare options, or help me understand this project.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Make something/i })).toBeInTheDocument();
    expect(screen.getByText('Create or improve something useful.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Guide me/i })).toBeInTheDocument();
    expect(screen.getByText('Help me finish a task one safe step at a time.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Guide me/i }));

    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith('Guide me through one safe first task');
  });
});
