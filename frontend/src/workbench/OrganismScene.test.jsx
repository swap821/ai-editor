import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import OrganismScene from './OrganismScene';

vi.mock('@/components/ui/BootSequence', () => ({
  default: ({ onComplete }) => <button onClick={onComplete}>Complete boot</button>,
}));

vi.mock('@/components/canvas/WorkspaceCanvas', () => ({
  default: ({ booted, physical, attentionTargetRef }) => (
    <div
      data-testid="workspace"
      data-booted={String(booted)}
      data-travel={physical?.conductor?.travel}
      data-has-target-ref={String(Boolean(attentionTargetRef))}
    />
  ),
}));

vi.mock('@/components/canvas/SuperbrainScene.LEGACY', () => ({
  SCENE_UNIFORMS: { uBreath: {} },
}));

vi.mock('./SuperbrainReactiveEffects', () => ({
  default: () => null,
}));

afterEach(cleanup);

describe('OrganismScene', () => {
  it('shows boot controls until boot completes and forwards the callback', () => {
    const onBootComplete = vi.fn();
    const { rerender } = render(
      <OrganismScene booted={false} onBootComplete={onBootComplete} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Complete boot' }));
    expect(onBootComplete).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('workspace').getAttribute('data-booted')).toBe('false');

    rerender(<OrganismScene booted onBootComplete={onBootComplete} />);
    expect(screen.queryByRole('button', { name: 'Complete boot' })).toBeNull();
    expect(screen.getByTestId('workspace').getAttribute('data-booted')).toBe('true');
  });

  it('passes physical state and the attention target ref to the workspace', () => {
    const attentionTargetRef = { current: null };

    render(
      <OrganismScene
        booted
        physical={{ conductor: { travel: 'frozen' } }}
        attentionTargetRef={attentionTargetRef}
      />,
    );

    const workspace = screen.getByTestId('workspace');
    expect(workspace.getAttribute('data-travel')).toBe('frozen');
    expect(workspace.getAttribute('data-has-target-ref')).toBe('true');
  });
});
