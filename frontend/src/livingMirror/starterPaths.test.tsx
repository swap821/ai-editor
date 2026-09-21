import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StarterPaths } from './StarterPaths';

describe('StarterPaths', () => {
  it('offers understandable paths and only returns the selected prompt', () => {
    const onChoose = vi.fn();
    render(<StarterPaths onChoose={onChoose} />);

    expect(screen.getByRole('group', { name: 'Choose how to begin' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Understand something/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Make something useful/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Guide me step by step/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Guide me step by step/i }));

    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith('Guide me through one safe first task');
  });
});
