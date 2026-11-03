import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import ErrorBoundary, { ErrorBoundary as NamedBoundary } from './ErrorBoundary';

let shouldThrow = true;

function Bomb() {
  if (shouldThrow) {
    throw new Error('kaboom failure');
  }
  return <div data-testid="healthy">All good</div>;
}

describe('ErrorBoundary', () => {
  let errorSpy;

  beforeEach(() => {
    shouldThrow = true;
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it('exports the same component as default and named export', () => {
    expect(ErrorBoundary).toBe(NamedBoundary);
  });

  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary name="Panel">
        <div data-testid="child">Hello</div>
      </ErrorBoundary>
    );

    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a labelled fallback with error details and logs the error', () => {
    render(
      <ErrorBoundary name="AlignmentPanel">
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('AlignmentPanel Error')).toBeInTheDocument();
    expect(screen.getByText('kaboom failure')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry AlignmentPanel' })).toBeInTheDocument();
    expect(screen.queryByTestId('healthy')).not.toBeInTheDocument();

    const call = errorSpy.mock.calls.find(
      (args) => args[0] === '[ErrorBoundary: AlignmentPanel]'
    );
    expect(call).toBeDefined();
    expect(call[1]).toBeInstanceOf(Error);
    expect(call[1].message).toBe('kaboom failure');
  });

  it('falls back to the generic label when no name is given', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByText('Component Error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry Component' })).toBeInTheDocument();
  });

  it('renders a custom fallback instead of the default UI', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="custom">Custom fallback</div>}>
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('custom')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('remounts children after Retry once the fault is cleared', () => {
    render(
      <ErrorBoundary name="Panel">
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: 'Retry Panel' }));

    expect(screen.getByTestId('healthy')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the fallback again when Retry re-trips the same fault', () => {
    render(
      <ErrorBoundary name="Panel">
        <Bomb />
      </ErrorBoundary>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Retry Panel' }));

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByTestId('healthy')).not.toBeInTheDocument();
  });
});
