import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { lazy, Suspense, type ReactElement } from 'react';
import { RendererFailureBoundary } from './RendererFailureBoundary';

function BrokenOrganism(): ReactElement {
  throw new Error('organism import failed');
}

describe('RendererFailureBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  it('keeps the product shell usable when the lazy organism fails before mounting', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <RendererFailureBoundary onRetry={() => {}}>
        <BrokenOrganism />
      </RendererFailureBoundary>,
    );

    expect(screen.getByTestId('renderer-fallback-notice')).toHaveTextContent(
      'GAGOS controls are still working.',
    );
    expect(screen.getByRole('button', { name: 'Retry visual organism' })).toBeInTheDocument();
  });

  it('keeps retry explicit and delegated to the shell', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const onRetry = vi.fn();

    render(
      <RendererFailureBoundary onRetry={onRetry}>
        <BrokenOrganism />
      </RendererFailureBoundary>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Retry visual organism' }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('catches a rejected lazy import outside Suspense', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const BrokenLazyOrganism = lazy(() => Promise.reject(new Error('lazy import failed')));

    render(
      <RendererFailureBoundary onRetry={() => {}}>
        <Suspense fallback={<p>Loading organism</p>}>
          <BrokenLazyOrganism />
        </Suspense>
      </RendererFailureBoundary>,
    );

    await waitFor(() => expect(screen.getByTestId('renderer-fallback-notice')).toBeInTheDocument());
    expect(screen.queryByText('Loading organism')).not.toBeInTheDocument();
  });
});
