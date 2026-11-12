import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MemoryHalo from './MemoryHalo';

const h = vi.hoisted(() => ({
  state: { motes: [] as unknown[], presentingId: null as number | null },
  listener: null as null | ((s: unknown) => void),
  unsubscribe: vi.fn(),
  stopPolling: vi.fn(),
  presentMote: vi.fn(),
  dismissPresentation: vi.fn(),
  absorbMote: vi.fn(() => Promise.resolve()),
  releaseMote: vi.fn(() => Promise.resolve()),
}));

vi.mock('@/lib/memoryHalo', () => ({
  HALO_TIMING: { absorb: 1, release: 1, flare: 1 },
  absorbMote: h.absorbMote,
  releaseMote: h.releaseMote,
  presentMote: h.presentMote,
  dismissPresentation: h.dismissPresentation,
  getHalo: () => h.state,
  installHaloDevHooks: vi.fn(),
  moteOrbitOffset: () => [0, 0, 0],
  retireMote: vi.fn(),
  settleFlare: vi.fn(),
  stampLifecycle: vi.fn(),
  startHaloPolling: () => h.stopPolling,
  subscribeHalo: (cb: (s: unknown) => void) => {
    h.listener = cb;
    return h.unsubscribe;
  },
}));

vi.mock('@/lib/spineFusionBus', () => ({
  getCortexAnchor: () => [0, 0, 0],
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: vi.fn(),
}));

vi.mock('@react-three/drei', () => ({
  Billboard: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Text: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
}));

function mote(id: number, subject: string) {
  return {
    proposal: { id, subject, predicate: 'likes', object: 'tea' },
    seed: id,
    lifecycle: 'orbiting',
    lifecycleAt: -1,
  };
}

describe('MemoryHalo', () => {
  beforeEach(() => {
    h.state = { motes: [], presentingId: null };
    h.listener = null;
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it('renders nothing without motes and cleans up its subscriptions on unmount', () => {
    const { container, unmount } = render(<MemoryHalo reducedMotion={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(h.unsubscribe).not.toHaveBeenCalled();
    unmount();
    expect(h.unsubscribe).toHaveBeenCalledOnce();
    expect(h.stopPolling).toHaveBeenCalledOnce();
  });

  it('shows motes pushed through the subscription, text only for the presented one', () => {
    const { container } = render(<MemoryHalo reducedMotion={false} />);
    act(() => {
      h.listener?.({ motes: [mote(1, 'Ada'), mote(2, 'Bob')], presentingId: 2 });
    });
    expect(container.querySelectorAll('group > group')).toHaveLength(2);
    expect(screen.getByText('Bob — likes — tea')).toBeInTheDocument();
    expect(screen.queryByText('Ada — likes — tea')).toBeNull();
    expect(screen.getByText('a memory asks to form')).toBeInTheDocument();
  });

  it('presents a mote on click, and dismisses when it is already presented', () => {
    h.state = { motes: [mote(7, 'Ada')], presentingId: null };
    const { container, unmount } = render(<MemoryHalo reducedMotion />);
    fireEvent.click(container.querySelector('mesh') as Element);
    expect(h.presentMote).toHaveBeenCalledWith(7);
    expect(h.dismissPresentation).not.toHaveBeenCalled();
    unmount();

    h.state = { motes: [mote(7, 'Ada')], presentingId: 7 };
    const second = render(<MemoryHalo reducedMotion />);
    fireEvent.click(second.container.querySelector('mesh') as Element);
    expect(h.dismissPresentation).toHaveBeenCalledOnce();
    expect(h.presentMote).toHaveBeenCalledTimes(1);
  });

  it('absorb and release nodes call their own actions with the mote id', () => {
    h.state = { motes: [mote(5, 'Ada')], presentingId: 5 };
    render(<MemoryHalo reducedMotion={false} />);

    const absorbHit = screen.getByText('absorb').parentElement?.querySelector('mesh') as Element;
    fireEvent.click(absorbHit);
    expect(h.absorbMote).toHaveBeenCalledWith(5);
    expect(h.releaseMote).not.toHaveBeenCalled();

    const releaseHit = screen.getByText('release').parentElement?.querySelector('mesh') as Element;
    fireEvent.click(releaseHit);
    expect(h.releaseMote).toHaveBeenCalledWith(5);
    expect(h.absorbMote).toHaveBeenCalledTimes(1);
  });
});
