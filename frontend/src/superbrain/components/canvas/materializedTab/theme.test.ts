import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { toSurfaceTheme } from './theme';

type Material = Parameters<typeof toSurfaceTheme>[0];

const palette = {
  reach: '#ff0000',
  live: '#00ff00',
  frame: '#0000ff',
  body: '#111111',
  header: '#222222',
  accent: '#333333',
  outline: '#444444',
  plate: '#555555',
  text: '#666666',
  muted: '#777777',
  point: '#888888',
};

function makeMaterial(overrides: Partial<typeof palette> = {}): Material {
  return { palette: { ...palette, ...overrides } } as unknown as Material;
}

describe('toSurfaceTheme', () => {
  it('converts reach, live and frame into THREE.Color instances with the matching hex', () => {
    const theme = toSurfaceTheme(makeMaterial());

    expect(theme.reach).toBeInstanceOf(THREE.Color);
    expect(theme.live).toBeInstanceOf(THREE.Color);
    expect(theme.frame).toBeInstanceOf(THREE.Color);
    expect(theme.reach.getHex()).toBe(0xff0000);
    expect(theme.live.getHex()).toBe(0x00ff00);
    expect(theme.frame.getHex()).toBe(0x0000ff);
  });

  it('passes the remaining palette entries through unchanged as strings', () => {
    const theme = toSurfaceTheme(makeMaterial());

    expect(theme.body).toBe('#111111');
    expect(theme.header).toBe('#222222');
    expect(theme.accent).toBe('#333333');
    expect(theme.outline).toBe('#444444');
    expect(theme.plate).toBe('#555555');
    expect(theme.text).toBe('#666666');
    expect(theme.muted).toBe('#777777');
    expect(theme.point).toBe('#888888');
  });

  it('maps each palette key to its own field', () => {
    const theme = toSurfaceTheme(
      makeMaterial({ reach: '#00ff00', live: '#0000ff', frame: '#ff0000', text: '#abcdef' }),
    );

    expect(theme.reach.getHex()).toBe(0x00ff00);
    expect(theme.live.getHex()).toBe(0x0000ff);
    expect(theme.frame.getHex()).toBe(0xff0000);
    expect(theme.text).toBe('#abcdef');
    expect(theme.body).toBe('#111111');
  });

  it('creates fresh colors on every call so mutating one theme does not affect another', () => {
    const material = makeMaterial();
    const first = toSurfaceTheme(material);
    const second = toSurfaceTheme(material);

    expect(first.reach).not.toBe(second.reach);

    first.reach.setHex(0x123456);

    expect(first.reach.getHex()).toBe(0x123456);
    expect(second.reach.getHex()).toBe(0xff0000);
    expect(material.palette.reach).toBe('#ff0000');
  });
});
