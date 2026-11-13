import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import MemoryParticles from './MemoryParticles';

const mocks = vi.hoisted(() => ({
  frame: null as null | ((state: { clock: { elapsedTime: number } }, delta: number) => void),
  listener: null as null | ((event: { type: string; intensity?: number }) => void),
  unsubscribe: vi.fn(),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (callback: typeof mocks.frame) => {
    mocks.frame = callback;
  },
}));

vi.mock('@/lib/cognitionBus', () => ({
  subscribeCognition: (listener: typeof mocks.listener) => {
    mocks.listener = listener;
    return mocks.unsubscribe;
  },
}));

vi.mock('./DecayAura', () => ({}));

vi.mock('./CoreGeometry', () => ({
  BASE_TILT_X: 0.2,
  BASE_TILT_Z: 0.3,
  PULSE_GAIN: 2,
  PULSE_DECAY_RATE: 1,
  createDiskData: () => ({
    positions: new Float32Array(3),
    angles: new Float32Array(1),
    offsets: new Float32Array(1),
    speeds: new Float32Array(1),
    phases: new Float32Array(1),
    sizes: new Float32Array(1),
    tints: new Float32Array(1),
    jitters: new Float32Array(1),
  }),
}));

function makeProps(): ComponentProps<typeof MemoryParticles> {
  return {
    activity: 0.5,
    burst: { current: { intensity: 0.4 } } as ComponentProps<typeof MemoryParticles>['burst'],
    arrival: { current: 0.7 },
  };
}

describe('MemoryParticles', () => {
  it('updates the material and group on a frame', () => {
    const { container } = render(<MemoryParticles {...makeProps()} />);
    const group = container.querySelector('group');
    const material = container.querySelector('decayAuraMaterial') as unknown as Record<string, number>;
    expect(group).not.toBeNull();
    expect(material).not.toBeNull();

    const rotation = { x: 0, z: 0 };
    Object.defineProperty(group, 'rotation', { value: rotation });
    expect(mocks.frame).not.toBeNull();

    act(() => {
      mocks.frame?.({ clock: { elapsedTime: 0 } }, 0.5);
    });

    expect(material.uActivity).toBeCloseTo(0.5);
    expect(material.uBurst).toBeCloseTo(0.4);
    expect(material.uArrival).toBeCloseTo(0.7);
    expect(material.uFlowTime).toBeCloseTo(0.5 * (0.72 + 0.5 * 0.6 + 0.4 * 0.55));
    expect(material.uPulse).toBe(1);
    expect(rotation.x).toBeCloseTo(0.2);
    expect(rotation.z).toBeCloseTo(0.33);
  });

  it('pulses for acquired knowledge, decays, and unsubscribes on unmount', () => {
    mocks.unsubscribe.mockClear();
    const { container, unmount } = render(<MemoryParticles {...makeProps()} />);
    const material = container.querySelector('decayAuraMaterial') as unknown as Record<string, number>;
    const group = container.querySelector('group');
    Object.defineProperty(group, 'rotation', { value: { x: 0, z: 0 } });

    expect(mocks.listener).not.toBeNull();
    act(() => {
      mocks.listener?.({ type: 'knowledge-acquired', intensity: 0.5 });
      mocks.frame?.({ clock: { elapsedTime: 0 } }, 0.5);
    });
    expect(material.uPulse).toBeCloseTo(1 + 0.8 * Math.exp(-0.5) * 2);

    act(() => {
      mocks.listener?.({ type: 'unrelated', intensity: 1 });
      mocks.frame?.({ clock: { elapsedTime: 0 } }, 0.5);
    });
    expect(material.uPulse).toBeCloseTo(1 + 0.8 * Math.exp(-1) * 2);

    unmount();
    expect(mocks.unsubscribe).toHaveBeenCalledOnce();
  });
});
