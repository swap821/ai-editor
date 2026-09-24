import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { RendererFallbackNotice } from './RendererFallbackNotice';
import {
  rendererFallbackVisible,
  setRendererFallbackPresentation,
} from './rendererFallbackPresentation';

describe('RendererFallbackNotice', () => {
  afterEach(() => {
    setRendererFallbackPresentation(false);
    document.body.innerHTML = '';
  });

  it('does not announce a renderer failure while the organism is available', () => {
    render(<RendererFallbackNotice />);

    expect(screen.queryByTestId('renderer-fallback-notice')).not.toBeInTheDocument();
  });

  it('communicates that the visual organism is unavailable without implying a backend failure', () => {
    setRendererFallbackPresentation(true);

    render(<RendererFallbackNotice />);

    const notice = screen.getByTestId('renderer-fallback-notice');
    expect(notice).toHaveTextContent('Visual organism unavailable.');
    expect(notice).toHaveTextContent('GAGOS controls are still working.');
    expect(notice).toHaveTextContent('Use the scene retry control to try again.');
  });

  it('treats the managed fallback boundary as the measured renderer signal', () => {
    const root = document.createElement('main');

    expect(rendererFallbackVisible(root)).toBe(false);
    root.innerHTML = '<div class="webgl-fallback"></div>';
    expect(rendererFallbackVisible(root)).toBe(true);
  });

  it('keeps retry as an explicit keyboard-accessible control when the shell owns recovery', () => {
    const onRetry = vi.fn();
    setRendererFallbackPresentation(true);

    render(<RendererFallbackNotice onRetry={onRetry} />);

    const retry = screen.getByRole('button', { name: 'Retry visual organism' });
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
