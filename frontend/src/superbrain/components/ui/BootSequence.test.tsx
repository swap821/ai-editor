import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

import BootSequence from './BootSequence';
import { ArrivalMode, transitionToArriving } from '@/lib/lifecycleStateMachine';

const reduced = vi.hoisted(() => ({ value: false }));
const progressState = vi.hoisted(() => ({ progress: 0 }));

vi.mock('@react-three/drei', () => ({
  useProgress: { getState: () => progressState },
}));

vi.mock('@/lib/lifecycleStateMachine', () => ({
  transitionToArriving: vi.fn(),
  ArrivalMode: { COALESCENCE: 'coalescence', AWAKENING: 'awakening' },
}));

vi.mock('@/lib/reducedMotion', () => ({
  useReducedMotion: () => reduced.value,
}));

vi.mock('@/lib/mirrorStore', () => ({
  useMirrorStore: { subscribe: () => () => {} },
}));

const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

describe('BootSequence', () => {
  beforeEach(() => {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame', 'performance'],
    });
    window.localStorage.clear();
    reduced.value = false;
    progressState.progress = 0;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('skips to the finale on pointerdown, then calls onComplete after the fade', () => {
    const onComplete = vi.fn();
    const { container } = render(<BootSequence onComplete={onComplete} />);

    fireEvent.pointerDown(window);
    advance(20);
    expect(screen.getByRole('status').textContent).toBe('LIVING MIRROR');
    expect(onComplete).not.toHaveBeenCalled();

    // Finale sweep is 420ms; it then moves to the fade phase.
    advance(420);
    expect(transitionToArriving).toHaveBeenCalledTimes(1);
    expect(transitionToArriving).toHaveBeenCalledWith(ArrivalMode.COALESCENCE);
    expect(onComplete).not.toHaveBeenCalled();

    // Fade is 500ms; then the component renders null and reports completion.
    advance(500);
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(container.firstChild).toBeNull();
  });

  it('uses the short reduced-motion timings and marks the overlay', () => {
    reduced.value = true;
    render(<BootSequence onComplete={() => {}} />);

    expect(screen.getByRole('status').getAttribute('data-reduced-motion')).toBe('true');

    // Reduced bar ceiling is 550ms; with no asset progress the log is still shown at 500ms.
    advance(500);
    expect(screen.getByRole('status').textContent).toContain('Preparing the visual organism');

    // Past the 550ms ceiling the finale sweep has begun (finale lasts 320ms).
    advance(100);
    expect(screen.getByRole('status').textContent).toBe('LIVING MIRROR');
  });

  it('shortens the sequence to the reduced ramp when assets report full progress', () => {
    reduced.value = true;
    progressState.progress = 100;
    render(<BootSequence onComplete={() => {}} />);

    // Before the 350ms ramp the log is still on screen.
    advance(300);
    expect(screen.getByRole('status').textContent).toContain('Preparing the visual organism');

    // After the ramp with progress at 100, the finale starts well before the 550ms ceiling.
    advance(100);
    expect(screen.getByRole('status').textContent).toBe('LIVING MIRROR');
  });
});
