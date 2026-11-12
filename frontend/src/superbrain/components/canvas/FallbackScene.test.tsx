import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FallbackScene } from './FallbackScene';

vi.mock('./FallbackScene.css', () => ({}));

describe('FallbackScene', () => {
  afterEach(() => {
    cleanup();
  });

  it('defaults to the idle posture', () => {
    const { container } = render(<FallbackScene />);
    const scene = container.firstElementChild as HTMLElement;

    expect(scene).toHaveClass('fallback-scene');
    expect(scene).toHaveClass('fallback-scene--idle');
  });

  it.each(['thinking', 'speaking', 'listening'] as const)(
    'applies the %s posture modifier class only',
    (posture) => {
      const { container } = render(<FallbackScene posture={posture} />);
      const scene = container.firstElementChild as HTMLElement;

      expect(scene).toHaveClass(`fallback-scene--${posture}`);
      expect(scene).not.toHaveClass('fallback-scene--idle');
    },
  );

  it('is hidden from assistive tech and contains the orb', () => {
    const { container } = render(<FallbackScene posture="speaking" />);
    const scene = container.firstElementChild as HTMLElement;

    expect(scene).toHaveAttribute('aria-hidden', 'true');
    expect(scene.querySelector('.fallback-scene__orb')).not.toBeNull();
  });
});
