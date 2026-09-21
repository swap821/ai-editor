import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WebGLErrorBoundary } from './WebGLErrorBoundary';

function ThrowingChild(): never {
  throw new Error('simulated renderer failure');
}

describe('WebGLErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks());

  it('keeps the conversation path available with an accessible fallback', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const onRetry = vi.fn();
    render(
      <WebGLErrorBoundary onRetry={onRetry}>
        <ThrowingChild />
      </WebGLErrorBoundary>,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('GAGOS is still here');
    expect(screen.getByRole('alert')).toHaveTextContent('Conversation and workspaces remain available.');
    fireEvent.click(screen.getByRole('button', { name: 'Retry 3D presence' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('preserves an explicit caller fallback', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <WebGLErrorBoundary fallback={<p>Caller fallback</p>}>
        <ThrowingChild />
      </WebGLErrorBoundary>,
    );
    expect(screen.getByText('Caller fallback')).toBeInTheDocument();
  });
});
