import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import DeliberationOverlay from './DeliberationOverlay';

type HudState = { activeCastes: string[] };

const hud = vi.hoisted(() => ({
  state: { activeCastes: [] as string[] },
  listener: null as ((s: { activeCastes: string[] }) => void) | null,
  unsubscribe: vi.fn(),
}));

vi.mock('@/lib/swarmHUDStore', () => ({
  getSwarmHUDState: () => hud.state,
  subscribeSwarmHUD: (cb: (s: { activeCastes: string[] }) => void) => {
    hud.listener = cb;
    return hud.unsubscribe;
  },
}));

vi.mock('./NerveMesh', () => ({
  default: ({ activeStates }: { activeStates: Float32Array }) => (
    <div
      data-testid="mesh"
      data-states={Array.from(activeStates).join(',')}
      data-float32={String(activeStates instanceof Float32Array)}
    />
  ),
  COUNCIL_NODES: [{ caste: 'scout' }, { caste: 'builder' }, { caste: 'warrior' }],
}));

function emit(state: HudState) {
  const listener = hud.listener;
  if (!listener) {
    throw new Error('overlay did not subscribe');
  }
  act(() => {
    listener(state);
  });
}

function states(): string | null {
  return screen.getByTestId('mesh').getAttribute('data-states');
}

describe('DeliberationOverlay', () => {
  beforeEach(() => {
    hud.state = { activeCastes: [] };
    hud.listener = null;
    hud.unsubscribe.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it('passes all-zero Float32Array states when no castes are active', () => {
    render(<DeliberationOverlay />);
    expect(states()).toBe('0,0,0');
    expect(screen.getByTestId('mesh').getAttribute('data-float32')).toBe('true');
  });

  it('activates nodes from the initial HUD state, matching case-insensitively by substring', () => {
    hud.state = { activeCastes: ['SCOUT-Alpha', 'Warrior'] };
    render(<DeliberationOverlay />);
    expect(states()).toBe('1,0,1');
  });

  it('updates the node states when the HUD pushes a new state', () => {
    hud.state = { activeCastes: ['Scout'] };
    render(<DeliberationOverlay />);
    expect(states()).toBe('1,0,0');

    emit({ activeCastes: ['Builder'] });
    expect(states()).toBe('0,1,0');

    emit({ activeCastes: ['unknown'] });
    expect(states()).toBe('0,0,0');
  });

  it('unsubscribes from the HUD on unmount', () => {
    const { unmount } = render(<DeliberationOverlay />);
    expect(hud.unsubscribe).not.toHaveBeenCalled();
    unmount();
    expect(hud.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
