import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SubsystemErrorBoundary } from './SubsystemErrorBoundary';

function ThrowingChild(): never {
  throw new Error('simulated subsystem failure');
}

describe('SubsystemErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks());

  it('renders its children when nothing throws', () => {
    render(
      <SubsystemErrorBoundary name="Stars">
        <p>Healthy subsystem</p>
      </SubsystemErrorBoundary>,
    );

    expect(screen.getByText('Healthy subsystem')).toBeInTheDocument();
  });

  it('renders nothing when a child throws, leaving siblings intact', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <div data-testid="host">
        <p>Sibling</p>
        <SubsystemErrorBoundary name="Stars">
          <ThrowingChild />
          <p>Never shown</p>
        </SubsystemErrorBoundary>
      </div>,
    );

    expect(screen.getByText('Sibling')).toBeInTheDocument();
    expect(screen.queryByText('Never shown')).not.toBeInTheDocument();
    expect(screen.getByTestId('host').children).toHaveLength(1);
  });

  it('logs the crash with the subsystem name and the original error', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <SubsystemErrorBoundary name="Nebula">
        <ThrowingChild />
      </SubsystemErrorBoundary>,
    );

    const call = errorSpy.mock.calls.find(
      (args) => args[0] === 'Subsystem [Nebula] crashed:',
    );
    expect(call).toBeDefined();
    const logged = call?.[1] as Error;
    expect(logged).toBeInstanceOf(Error);
    expect(logged.message).toBe('simulated subsystem failure');
    expect(call?.[2]).toHaveProperty('componentStack');
  });

  it('derives error state from a thrown error', () => {
    const error = new Error('boom');
    expect(SubsystemErrorBoundary.getDerivedStateFromError(error)).toEqual({
      hasError: true,
      error,
    });
  });
});
