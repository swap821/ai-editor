import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { BeingStatus } from './BeingStatus';
import type { BeingPresentation } from './beingPresentation';

type Continuity = BeingPresentation['continuityState'];
type TaskState = ComponentProps<typeof BeingStatus>['taskState'];

const continuity = 'test-continuity' as unknown as Continuity;
const idle: TaskState = 'idle';

function presentation(overrides: Partial<BeingPresentation>): BeingPresentation {
  return {
    phase: 'ready',
    continuityState: continuity,
    workerCount: 0,
    ...overrides,
  } as BeingPresentation;
}

afterEach(() => {
  cleanup();
});

describe('BeingStatus', () => {
  it('shows the phase label, phase attribute and live region without expert details', () => {
    const { container } = render(
      <BeingStatus presentation={presentation({ phase: 'listening' })} taskState={idle} />,
    );

    expect(screen.getByText('Listening')).not.toBeNull();

    const root = container.firstElementChild;
    expect(root?.getAttribute('data-being-phase')).toBe('listening');
    expect(root?.getAttribute('aria-live')).toBe('polite');
    expect(screen.queryByText(/temporary worker/)).toBeNull();
  });

  it('shows a singular worker count in expert mode', () => {
    render(
      <BeingStatus
        presentation={presentation({ phase: 'acting', workerCount: 1 })}
        taskState={idle}
        expert
      />,
    );

    expect(screen.getByText('Working')).not.toBeNull();
    expect(screen.getByText(`acting · ${continuity} · 1 temporary worker`)).not.toBeNull();
  });

  it('pluralises the worker count in expert mode when there are several workers', () => {
    render(
      <BeingStatus
        presentation={presentation({ phase: 'planning', workerCount: 2 })}
        taskState={idle}
        expert
      />,
    );

    expect(screen.getByText('Preparing')).not.toBeNull();
    expect(screen.getByText(`planning · ${continuity} · 2 temporary workers`)).not.toBeNull();
  });
});
