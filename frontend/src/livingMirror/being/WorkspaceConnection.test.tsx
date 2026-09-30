import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRef } from 'react';
import { Matrix4, PerspectiveCamera } from 'three';
import { WorkspaceConnectionOverlay, WorkspaceConnectionProjection } from './WorkspaceConnectionOverlay';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix, setSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel } from '../../superbrain/lib/tabStore';

let frame: (state: { camera: PerspectiveCamera; gl: { domElement: HTMLCanvasElement } }) => void;
// WebGL is external to this DOM integration test. Keep the real seat store,
// fusion/matrix publication, camera projection and resulting SVG geometry.
vi.mock('@react-three/fiber', () => ({ useFrame: (callback: typeof frame) => { frame = callback; } }));
const camera = new PerspectiveCamera(90, 1, 0.1, 100);
camera.position.set(0, 0, 10);
camera.updateMatrixWorld();
const overlayRef = createRef<SVGSVGElement>();

function Surface({ renderer = true }: { renderer?: boolean }) {
  return <div className="lm-app">
    <canvas /><section className="lm-surface" />
    <WorkspaceConnectionOverlay overlayRef={overlayRef} />
    {renderer && <WorkspaceConnectionProjection overlayRef={overlayRef} snapshot={getTabStoreSnapshot()} />}
  </div>;
}
function step() {
  act(() => frame({ camera, gl: { domElement: document.querySelector('canvas')! } }));
}
function path() { return overlayRef.current!.querySelector('path')!.getAttribute('d'); }

beforeEach(() => {
  __resetTabStoreForTests();
  __resetSpineFusionForTests();
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const value = this.matches('canvas') ? { x: 100, y: 50, width: 400, height: 400 }
      : this.matches('.lm-surface') ? { x: 600, y: 100, width: 600, height: 600 }
        : { x: 20, y: 10, width: 1200, height: 800 };
    return { ...value, left: value.x, top: value.y, right: value.x + value.width, bottom: value.y + value.height, toJSON: () => value };
  });
  setSpineFusion(1, [0, 0, 0]);
  setBodyGroupWorldMatrix(new Matrix4());
  openWorkspacePanel('history', 'Recent observations');
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); __resetTabStoreForTests(); __resetSpineFusionForTests();
});

describe('body-to-workplane connection', () => {
  it('follows actual workspace focus and removes the connection on Conversation', () => {
    const view = render(<Surface />);
    step();
    const first = path();
    expect(first).toMatch(/^M 280 /);
    act(() => openWorkspacePanel('terminal', 'Terminal'));
    view.rerender(<Surface />); step();
    expect(path()).not.toBe(first);
    act(() => focusWorkspace('history'));
    view.rerender(<Surface />); step();
    expect(path()).toBe(first);
    act(() => focusWorkspace(null));
    view.rerender(<Surface />); step();
    expect(path()).toBe('');
    expect(overlayRef.current).toHaveAttribute('aria-hidden', 'true');
  });
  it('does not draw from a fabricated pre-load body matrix or after explicit close', () => {
    __resetSpineFusionForTests();
    const view = render(<Surface />); step();
    expect(path()).toBe('');
    setSpineFusion(1, [0, 0, 0]); setBodyGroupWorldMatrix(new Matrix4()); step();
    expect(path()).not.toBe('');
    act(() => closeWorkspace('history'));
    view.rerender(<Surface />); step();
    expect(path()).toBe('');
  });
  it('clears the old geometry when the renderer unmounts, without touching workspace records', () => {
    const view = render(<Surface />); step();
    expect(path()).not.toBe('');
    view.rerender(<Surface renderer={false} />);
    expect(path()).toBe('');
    expect(overlayRef.current).toHaveStyle({ visibility: 'hidden' });
    expect(getTabStoreSnapshot().focusId).toBe('history');
    expect(getTabStoreSnapshot().panels?.[0].open).toBe(true);
    view.rerender(<Surface />); step();
    expect(path()).not.toBe('');
  });
  it('refreshes the measured edge on resize, without changing the selected seat', () => {
    const view = render(<Surface />); step();
    const plane = view.container.querySelector('.lm-surface')!;
    Object.defineProperty(plane, 'getBoundingClientRect', { configurable: true,
      value: () => ({ left: 700, top: 100, width: 500, height: 600 }),
    });
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect(path()).toMatch(/, 678 [\d.]+$/);
    expect(getTabStoreSnapshot().panels?.[0].seatIndex).toBe(2);
  });
});
