import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AmbientFloat from './AmbientFloat';

type FrameCallback = (state: unknown, delta: number) => void;

const frame = vi.hoisted(() => ({ callback: null as null | ((state: unknown, delta: number) => void) }));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: FrameCallback) => {
    frame.callback = cb;
  },
}));

interface FakeGroup {
  rotation: { set: ReturnType<typeof vi.fn> };
  position: { y: number };
  updateMatrix: ReturnType<typeof vi.fn>;
}

function renderFloat(props: { paused?: boolean; speed?: number; rotationIntensity?: number; floatIntensity?: number }) {
  const { container } = render(
    <AmbientFloat
      paused={props.paused ?? false}
      speed={props.speed ?? 2}
      rotationIntensity={props.rotationIntensity ?? 1}
      floatIntensity={props.floatIntensity ?? 1}
    >
      <span>body</span>
    </AmbientFloat>,
  );
  const inner = container.querySelector('group > group');
  if (!inner) throw new Error('inner group missing');
  const fake: FakeGroup = {
    rotation: { set: vi.fn() },
    position: { y: 0 },
    updateMatrix: vi.fn(),
  };
  Object.assign(inner, fake);
  return fake;
}

function tick(delta: number) {
  if (!frame.callback) throw new Error('useFrame was not registered');
  frame.callback({}, delta);
}

describe('AmbientFloat', () => {
  beforeEach(() => {
    frame.callback = null;
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  it('renders its children', () => {
    renderFloat({});
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('applies the bob from the accumulated phase and scales by intensity', () => {
    const fake = renderFloat({ speed: 2, rotationIntensity: 2, floatIntensity: 3 });
    tick(2); // phase = 2 * 2 / 4 = 1
    const phase = 1;
    expect(fake.rotation.set).toHaveBeenCalledWith(
      (Math.cos(phase) / 8) * 2,
      (Math.sin(phase) / 8) * 2,
      (Math.sin(phase) / 20) * 2,
    );
    expect(fake.position.y).toBeCloseTo((Math.sin(phase) / 10) * 3, 10);
    expect(fake.updateMatrix).toHaveBeenCalledOnce();
  });

  it('accumulates phase across frames', () => {
    const fake = renderFloat({ speed: 4, floatIntensity: 1 });
    tick(1);
    tick(1); // phase = 2
    expect(fake.position.y).toBeCloseTo(Math.sin(2) / 10, 10);
    expect(fake.updateMatrix).toHaveBeenCalledTimes(2);
  });

  it('does nothing while paused or when speed is zero', () => {
    const paused = renderFloat({ paused: true });
    tick(1);
    expect(paused.rotation.set).not.toHaveBeenCalled();
    expect(paused.updateMatrix).not.toHaveBeenCalled();
    expect(paused.position.y).toBe(0);

    document.body.innerHTML = '';
    const still = renderFloat({ speed: 0 });
    tick(1);
    expect(still.rotation.set).not.toHaveBeenCalled();
    expect(still.updateMatrix).not.toHaveBeenCalled();
  });
});
