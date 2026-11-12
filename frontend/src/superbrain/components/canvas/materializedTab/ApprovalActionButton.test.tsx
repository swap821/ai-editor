// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ApprovalActionButton } from './ApprovalActionButton';

vi.mock('@react-three/drei', () => ({
  Text: ({ children }: { children?: React.ReactNode }) => (
    <span data-testid="label">{children}</span>
  ),
}));

afterEach(() => {
  cleanup();
});

function setup(disabled: boolean) {
  const onActivate = vi.fn();
  const onParentClick = vi.fn();
  const { container } = render(
    <div onClick={onParentClick}>
      <ApprovalActionButton
        label="APPROVE"
        position={[0, 0, 0]}
        fill="#00ff00"
        outline="#ffffff"
        disabled={disabled}
        onActivate={onActivate}
      />
    </div>,
  );
  const group = container.querySelector('group') as HTMLElement;
  return { group, onActivate, onParentClick };
}

describe('ApprovalActionButton', () => {
  it('renders the label text', () => {
    setup(false);
    expect(screen.getByTestId('label').textContent).toBe('APPROVE');
  });

  it('calls onActivate once on click and stops propagation when enabled', () => {
    const { group, onActivate, onParentClick } = setup(false);
    fireEvent.click(group);
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it('does not call onActivate when disabled, but still stops propagation', () => {
    const { group, onActivate, onParentClick } = setup(true);
    fireEvent.click(group);
    expect(onActivate).not.toHaveBeenCalled();
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it('scales up on hover and back down on pointer out when enabled', () => {
    const { group } = setup(false);
    expect(group.getAttribute('scale')).toBe('1');
    fireEvent.pointerOver(group);
    expect(group.getAttribute('scale')).toBe('1.04');
    fireEvent.pointerOut(group);
    expect(group.getAttribute('scale')).toBe('1');
  });

  it('does not scale on hover when disabled', () => {
    const { group } = setup(true);
    fireEvent.pointerOver(group);
    expect(group.getAttribute('scale')).toBe('1');
  });
});
