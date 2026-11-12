import { cleanup, render } from '@testing-library/react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CommandNerve3D from './CommandNerve3D';

type FrameCallback = (state: unknown, delta: number) => void;

const mocks = vi.hoisted(() => ({
  frame: null as unknown,
  funnel: vi.fn(),
  phaseHue: vi.fn(),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: unknown) => {
    mocks.frame = cb;
  },
}));

vi.mock('@/lib/funnelAnchorBus', () => ({
  getFunnelAnchor: () => mocks.funnel(),
}));

vi.mock('@/lib/phaseWeather', () => ({
  getWeather: () => ({}),
  installWeather: () => {},
  phaseHueOf: () => mocks.phaseHue(),
}));

interface FakeMaterial {
  color: THREE.Color;
  opacity: number;
  emissiveIntensity: number;
}

function mountNerve() {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const { container } = render(<CommandNerve3D reducedMotion={false} />);
  const material = container.querySelector('meshstandardmaterial') as unknown as FakeMaterial;
  const groups = Array.from(container.querySelectorAll('group')) as unknown as { visible?: boolean }[];
  const mesh = container.querySelector('mesh') as unknown as { visible?: boolean };
  material.color = new THREE.Color('#b06eff');
  return { material, groups, mesh, runFrame: mocks.frame as FrameCallback };
}

describe('CommandNerve3D', () => {
  beforeEach(() => {
    mocks.funnel.mockReturnValue({
      visible: false,
      intake: 1,
      flow: 1,
      world: [0, 0, 0],
    });
    mocks.phaseHue.mockReturnValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    delete (window as { __NERVE_DRIVE?: unknown }).__NERVE_DRIVE;
    document.body.innerHTML = '';
  });

  it('hides the tube, both junction nodes and the beads when the being is not visible', () => {
    const { mesh, groups, runFrame } = mountNerve();

    runFrame({}, 0.016);

    expect(mesh.visible).toBe(false);
    // groups: [outer, button node, socket node, bead group]
    expect(groups[1].visible).toBe(false);
    expect(groups[2].visible).toBe(false);
    expect(groups[3].visible).toBe(false);
  });

  it('hides everything when presence is zero or non-finite, even at full drive', () => {
    const button = document.createElement('button');
    button.className = 'gagos-send';
    document.body.appendChild(button);
    (window as { __NERVE_DRIVE?: { drive: number; flow: number } }).__NERVE_DRIVE = { drive: 1, flow: 1 };

    for (const presence of [0, Number.NaN]) {
      mocks.funnel.mockReturnValue({
        visible: true,
        intake: 1,
        flow: 1,
        presence,
        world: [0, 0, 0],
      });
      const { mesh, groups, runFrame } = mountNerve();

      runFrame({}, 10);

      expect(mesh.visible).toBe(false);
      expect(groups[1].visible).toBe(false);
      expect(groups[2].visible).toBe(false);
      expect(groups[3].visible).toBe(false);
      cleanup();
    }
  });

  it('tints the tube 35% toward the phase hue, and returns to canon purple without one', () => {
    mocks.phaseHue.mockReturnValue('#00ff00');
    const { material, runFrame } = mountNerve();

    // delta 0.4 * 2.5 clamps the damping factor to 1, so the colour reaches its target
    runFrame({}, 0.4);

    const tinted = new THREE.Color('#b06eff').lerp(new THREE.Color('#00ff00'), 0.35);
    expect(material.color.getHex()).toBe(tinted.getHex());
    expect(material.color.getHex()).not.toBe(new THREE.Color('#b06eff').getHex());

    mocks.phaseHue.mockReturnValue(undefined);
    runFrame({}, 0.4);

    expect(material.color.getHex()).toBe(new THREE.Color('#b06eff').getHex());
  });
});
