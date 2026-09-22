import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ExperienceModeSwitch } from './ExperienceModeSwitch';

describe('ExperienceModeSwitch', () => {
  it('marks Beginner as the safe guided default and explains the current surface', () => {
    render(<ExperienceModeSwitch mode="beginner" onChange={vi.fn()} />);

    expect(screen.getByRole('group', { name: 'Experience mode' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Beginner' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Expert / Mirror' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Guided front door')).toBeInTheDocument();
  });

  it('emits the explicit Expert choice without changing backend authority', () => {
    const onChange = vi.fn();
    render(<ExperienceModeSwitch mode="beginner" onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));

    expect(onChange).toHaveBeenCalledWith('expert');
  });
});
