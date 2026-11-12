import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import HorizonGlow from './HorizonGlow';

const frame = vi.hoisted(() => ({ cb: null as null | (() => void) }));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: () => void) => {
    frame.cb = cb;
  },
}));

type FakeMaterial = HTMLElement & { uniforms: { uOpacity: { value: number } } };
type DialWindow = { __GAGOS?: { horizon?: number } };

function setup() {
  const { container } = render(<HorizonGlow />);
  const material = container.querySelector('shadermaterial') as FakeMaterial;
  // In jsdom the ref resolves to a plain element; give it the uniforms the real material would have.
  material.uniforms = { uOpacity: { value: 0.16 } };
  return material;
}

function runFrame() {
  if (!frame.cb) throw new Error('useFrame callback was not registered');
  frame.cb();
}

describe('HorizonGlow', () => {
  beforeEach(() => {
    frame.cb = null;
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    delete (window as unknown as DialWindow).__GAGOS;
    vi.restoreAllMocks();
  });

  it('copies the dial horizon value into the opacity uniform each frame', () => {
    const material = setup();
    (window as unknown as DialWindow).__GAGOS = { horizon: 0.42 };
    runFrame();
    expect(material.uniforms.uOpacity.value).toBe(0.42);
  });

  it('applies a horizon of zero rather than treating it as missing', () => {
    const material = setup();
    (window as unknown as DialWindow).__GAGOS = { horizon: 0 };
    runFrame();
    expect(material.uniforms.uOpacity.value).toBe(0);
  });

  it('leaves opacity alone when no dial or horizon is present', () => {
    const material = setup();
    runFrame();
    expect(material.uniforms.uOpacity.value).toBe(0.16);

    (window as unknown as DialWindow).__GAGOS = {};
    runFrame();
    expect(material.uniforms.uOpacity.value).toBe(0.16);
  });
});
