import { cleanup, render } from '@testing-library/react';
import { PerspectiveCamera } from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PresenceViewport from './PresenceViewport';

const three = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  frame: null as null | (() => void),
}));

vi.mock('@react-three/fiber', () => ({
  useThree: (selector: (state: Record<string, unknown>) => unknown) => selector(three.state),
  useFrame: (callback: () => void) => {
    three.frame = callback;
  },
}));

vi.mock('@/lib/reducedMotion', () => ({
  useReducedMotion: () => false,
}));

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left, top, width, height,
    x: left, y: top,
    right: left + width, bottom: top + height,
    toJSON: () => ({}),
  };
}

describe('PresenceViewport', () => {
  let host: HTMLDivElement;
  let pane: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let camera: PerspectiveCamera;

  beforeEach(() => {
    host = document.createElement('div');
    host.className = 'lm-app';
    host.setAttribute('data-working', 'true');
    pane = document.createElement('div');
    pane.className = 'lm-scene';
    canvas = document.createElement('canvas');
    host.append(pane, canvas);
    document.body.append(host);
    vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(rect(300, 50, 700, 500));
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 1000, 600));
    camera = new PerspectiveCamera(50, 1, 0.1, 100);
    three.frame = null;
    three.state = { camera, gl: { domElement: canvas }, invalidate: vi.fn() };
  });

  afterEach(() => {
    cleanup();
    host.remove();
    vi.restoreAllMocks();
  });

  it('projects the camera onto the presence pane inside the stage and flags the refs', () => {
    const phoneFocusRef = { current: false };
    const workPaneRef = { current: false };
    render(<PresenceViewport phoneFocusRef={phoneFocusRef} workPaneRef={workPaneRef} />);

    expect(camera.view).toMatchObject({
      enabled: true,
      fullWidth: 700,
      fullHeight: 500,
      offsetX: -300,
      offsetY: -50,
      width: 1000,
      height: 600,
    });
    expect(phoneFocusRef.current).toBe(true);
    expect(workPaneRef.current).toBe(true);
  });

  it('restores the pane projection on each frame after something else overwrites it', () => {
    render(<PresenceViewport />);
    expect(three.frame).toBeTypeOf('function');

    camera.clearViewOffset();
    camera.aspect = 2;
    three.frame?.();

    expect(camera.view?.enabled).toBe(true);
    expect(camera.view?.fullWidth).toBe(700);
    expect(camera.view?.offsetX).toBe(-300);
  });

  it('leaves the camera alone when the pane has no drawable size', () => {
    vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 0, 0));
    const workPaneRef = { current: false };
    render(<PresenceViewport workPaneRef={workPaneRef} />);

    expect(camera.view).toBeNull();
    expect(workPaneRef.current).toBe(false);
  });

  it('restores the original camera and clears the refs on unmount', () => {
    const phoneFocusRef = { current: false };
    const workPaneRef = { current: false };
    const { unmount } = render(
      <PresenceViewport phoneFocusRef={phoneFocusRef} workPaneRef={workPaneRef} />,
    );
    expect(camera.view?.enabled).toBe(true);

    unmount();

    expect(camera.view?.enabled).toBe(false);
    expect(camera.aspect).toBe(1);
    expect(phoneFocusRef.current).toBe(false);
    expect(workPaneRef.current).toBe(false);
    expect(three.frame).toBeTypeOf('function');
  });
});
