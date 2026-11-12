import { describe, it, expect, vi } from 'vitest';
import * as THREE from 'three';
import { DecayAuraMaterial } from './DecayAura';
import { OUTER_RADIUS, INNER_RADIUS, INFALL_PERIOD, SPIN_TURNS, TAU } from './CoreGeometry';

const captured = vi.hoisted(() => ({
  shaderArgs: null as unknown[] | null,
  extended: null as Record<string, unknown> | null,
}));

vi.mock('@react-three/drei', () => ({
  shaderMaterial: (...args: unknown[]) => {
    captured.shaderArgs = args;
    return class FakeDecayMaterial {};
  },
}));

vi.mock('@react-three/fiber', () => ({
  extend: (objects: Record<string, unknown>) => {
    captured.extended = objects;
  },
}));

function getArgs(): {
  uniforms: Record<string, unknown>;
  vertex: string;
  fragment: string;
} {
  if (!captured.shaderArgs) throw new Error('shaderMaterial was never called');
  const [uniforms, vertex, fragment] = captured.shaderArgs as [
    Record<string, unknown>,
    string,
    string,
  ];
  return { uniforms, vertex, fragment };
}

describe('DecayAuraMaterial', () => {
  it('registers the exported material class with the renderer under its own name', () => {
    expect(typeof DecayAuraMaterial).toBe('function');
    expect(captured.extended).not.toBeNull();
    expect(Object.keys(captured.extended ?? {})).toEqual(['DecayAuraMaterial']);
    expect(captured.extended?.DecayAuraMaterial).toBe(DecayAuraMaterial);
  });

  it('starts with the documented resting uniform values', () => {
    const { uniforms } = getArgs();

    expect(uniforms.uFlowTime).toBe(0);
    expect(uniforms.uActivity).toBe(0);
    expect(uniforms.uBurst).toBe(0);
    expect(uniforms.uPulse).toBe(1);
    expect(uniforms.uArrival).toBe(0);
    expect(uniforms.uPostureTint).toBe(0);

    const color = uniforms.uPostureColor;
    expect(color).toBeInstanceOf(THREE.Color);
    const c = color as THREE.Color;
    expect(c.r).toBeCloseTo(150 / 255, 5);
    expect(c.g).toBeCloseTo(120 / 255, 5);
    expect(c.b).toBeCloseTo(1, 5);
  });

  it('bakes the core geometry constants into the vertex shader', () => {
    const { vertex } = getArgs();

    expect(vertex).toContain(`/ ${INFALL_PERIOD.toFixed(1)}`);
    expect(vertex).toContain(
      `mix(${OUTER_RADIUS.toFixed(2)}, ${INNER_RADIUS.toFixed(2)}, infall)`
    );
    expect(vertex).toContain(`(radius - ${INNER_RADIUS.toFixed(2)}) / ${(OUTER_RADIUS - INNER_RADIUS).toFixed(2)}`);
    expect(vertex).toContain(`* ${(SPIN_TURNS * TAU).toFixed(4)}`);
    expect(vertex).not.toContain('undefined');
    expect(vertex).not.toContain('NaN');
  });

  it('declares every uniform in the shader stage that consumes it', () => {
    const { uniforms, vertex, fragment } = getArgs();
    const fragmentOnly = ['uPostureColor', 'uPostureTint'];

    for (const name of Object.keys(uniforms)) {
      if (fragmentOnly.includes(name)) {
        expect(fragment).toMatch(new RegExp(`uniform \\w+ ${name};`));
      } else {
        expect(vertex).toMatch(new RegExp(`uniform float ${name};`));
      }
    }
    expect(fragment).toContain('void main()');
    expect(vertex).toContain('void main()');
  });
});
