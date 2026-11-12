// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SwarmHUD from './SwarmHUD';

interface HudState {
  active: boolean;
  plan: string[];
  activeCastes: string[];
  completedLegs: number;
  cloudIndices: number[];
}

const hud = vi.hoisted(() => ({
  state: {
    active: false,
    plan: [],
    activeCastes: [],
    completedLegs: 0,
    cloudIndices: [],
  } as HudState,
  listeners: [] as Array<(s: HudState) => void>,
  unsubscribed: 0,
}));

vi.mock('@/lib/swarmHUDStore', () => ({
  getSwarmHUDState: () => hud.state,
  subscribeSwarmHUD: (cb: (s: HudState) => void) => {
    hud.listeners.push(cb);
    return () => {
      hud.unsubscribed += 1;
      hud.listeners = hud.listeners.filter((l) => l !== cb);
    };
  },
}));

function makeState(overrides: Partial<HudState>): HudState {
  return {
    active: true,
    plan: [],
    activeCastes: [],
    completedLegs: 0,
    cloudIndices: [],
    ...overrides,
  };
}

beforeEach(() => {
  hud.state = makeState({ active: false });
  hud.listeners = [];
  hud.unsubscribed = 0;
});

afterEach(() => {
  cleanup();
});

describe('SwarmHUD', () => {
  it('renders nothing when inactive or when the plan is empty', () => {
    hud.state = makeState({ active: false, plan: ['a', 'b'] });
    const first = render(<SwarmHUD />);
    expect(first.container.innerHTML).toBe('');
    first.unmount();

    hud.state = makeState({ active: true, plan: [] });
    const second = render(<SwarmHUD />);
    expect(second.container.innerHTML).toBe('');
  });

  it('renders counts, pill states, cloud marker and caste line', () => {
    hud.state = makeState({
      plan: ['Research', 'Write code', 'Review'],
      activeCastes: ['worker-2-x', 'scout'],
      completedLegs: 1,
      cloudIndices: [1],
    });
    const { container } = render(<SwarmHUD />);

    const region = screen.getByRole('status', { name: 'Swarm progress' });
    expect(region.querySelector('.swarm-hud__title')?.textContent).toBe('SWARM');
    expect(region.querySelector('.swarm-hud__counts')?.textContent).toBe(
      '3 subtasks · 1 cloud · 1 done',
    );

    const pills = container.querySelectorAll('li');
    expect(pills).toHaveLength(3);
    expect(pills[0].className).toBe('swarm-hud__pill is-done');
    expect(pills[1].className).toBe('swarm-hud__pill is-active is-cloud');
    expect(pills[2].className).toBe('swarm-hud__pill');

    expect(pills[1].getAttribute('title')).toBe('Write code');
    expect(pills[1].querySelector('.swarm-hud__index')?.textContent).toBe('2');
    expect(pills[1].querySelector('.swarm-hud__label')?.textContent).toBe('Write code');

    expect(pills[0].querySelector('[aria-label="cloud"]')).toBeNull();
    expect(pills[1].querySelector('[aria-label="cloud"]')).not.toBeNull();

    expect(container.querySelector('.swarm-hud__caste')?.textContent).toBe(
      'WORKER-2-X · SCOUT',
    );
  });

  it('uses singular wording and omits optional parts when empty', () => {
    hud.state = makeState({ plan: ['Only task'] });
    const { container } = render(<SwarmHUD />);

    expect(container.querySelector('.swarm-hud__counts')?.textContent).toBe('1 subtask');
    expect(container.querySelector('.swarm-hud__caste')).toBeNull();
    expect(container.querySelector('li')?.className).toBe('swarm-hud__pill');
  });

  it('reacts to subscription updates and unsubscribes on unmount', () => {
    const { container, unmount } = render(<SwarmHUD />);
    expect(container.innerHTML).toBe('');
    expect(hud.listeners).toHaveLength(1);

    act(() => {
      hud.listeners[0](makeState({ plan: ['One', 'Two'], completedLegs: 2 }));
    });
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.querySelector('.swarm-hud__counts')?.textContent).toBe(
      '2 subtasks · 2 done',
    );
    expect(container.querySelectorAll('.is-done')).toHaveLength(2);

    act(() => {
      hud.listeners[0](makeState({ active: false, plan: ['One', 'Two'] }));
    });
    expect(container.innerHTML).toBe('');

    unmount();
    expect(hud.unsubscribed).toBe(1);
    expect(hud.listeners).toHaveLength(0);
  });
});
