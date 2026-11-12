import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CognitiveGrasp, { trailForSlot } from './CognitiveGrasp';
import { useFrame } from '@react-three/fiber';

const mocks = vi.hoisted(() => ({
  getKnownTrails: vi.fn<() => unknown[]>(() => []),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: vi.fn(),
}));

vi.mock('@/lib/aiosAdapter', () => ({
  getKnownTrails: mocks.getKnownTrails,
  trailLabel: vi.fn(() => 'label'),
}));

const trailA = { id: 'a' };
const trailB = { id: 'b' };
const trailC = { id: 'c' };

describe('CognitiveGrasp', () => {
  beforeEach(() => {
    mocks.getKnownTrails.mockReset();
    mocks.getKnownTrails.mockImplementation(() => []);
    vi.mocked(useFrame).mockClear();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('trailForSlot cycles through the known trails by slot', () => {
    mocks.getKnownTrails.mockImplementation(() => [trailA, trailB, trailC]);
    expect(trailForSlot(0)).toBe(trailA);
    expect(trailForSlot(1)).toBe(trailB);
    expect(trailForSlot(5)).toBe(trailC);
    expect(trailForSlot(7)).toBe(trailB);
  });

  it('trailForSlot returns null when no trails are known', () => {
    expect(trailForSlot(3)).toBeNull();
  });

  it('renders nothing while no trails are known', () => {
    const { container } = render(<CognitiveGrasp activity={0.5} />);
    expect(container.firstChild).toBeNull();
    expect(vi.mocked(useFrame)).not.toHaveBeenCalled();
  });

  it('renders a route and a target per anchor when trails exist', () => {
    mocks.getKnownTrails.mockImplementation(() => [trailA]);
    const { container } = render(<CognitiveGrasp activity={0.5} />);
    expect(container.firstChild).not.toBeNull();
    // 4 targets, each with a TransferRoute and a KnowledgeTarget frame loop.
    expect(vi.mocked(useFrame)).toHaveBeenCalledTimes(8);
  });

  it('wakes up on the 5s poll once the adapter learns a trail', () => {
    vi.useFakeTimers();
    const { container } = render(<CognitiveGrasp activity={0} />);
    expect(container.firstChild).toBeNull();

    mocks.getKnownTrails.mockImplementation(() => [trailA]);
    act(() => {
      vi.advanceTimersByTime(4999);
    });
    expect(container.firstChild).toBeNull();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(container.firstChild).not.toBeNull();
  });

  it('goes dormant again when trails disappear', () => {
    vi.useFakeTimers();
    mocks.getKnownTrails.mockImplementation(() => [trailA]);
    const { container } = render(<CognitiveGrasp activity={0} />);
    expect(container.firstChild).not.toBeNull();

    mocks.getKnownTrails.mockImplementation(() => []);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(container.firstChild).toBeNull();
  });
});
