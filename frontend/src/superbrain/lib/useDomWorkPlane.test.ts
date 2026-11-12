import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDomWorkPlane } from './useDomWorkPlane';

type Tab = Parameters<typeof useDomWorkPlane>[0];

const state = vi.hoisted(() => ({
  canvas: document.createElement('canvas'),
  invalidate: vi.fn(),
  tabs: [] as Array<{ id: string; lifecycle: string }>,
}));

vi.mock('@react-three/fiber', () => ({
  useThree: (selector: (s: unknown) => unknown) =>
    selector({ gl: { domElement: state.canvas }, invalidate: state.invalidate }),
}));

vi.mock('./tabStore', () => ({
  getTabStoreSnapshot: () => ({ tabs: state.tabs }),
}));

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

function makeTab(overrides: Record<string, unknown> = {}): Tab {
  return { id: 't1', kind: 'content', lifecycle: 'live', ...overrides } as unknown as Tab;
}

function mountSurface(workspaceId: string): HTMLElement {
  const host = document.querySelector('.lm-app') as HTMLElement;
  const surface = document.createElement('div');
  surface.className = 'lm-surface';
  surface.setAttribute('data-workspace-id', workspaceId);
  surface.getBoundingClientRect = () => rect(10, 10, 100, 100);
  host.appendChild(surface);
  return surface;
}

describe('useDomWorkPlane', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div class="lm-app"></div>';
    document.querySelector('.lm-app')?.appendChild(state.canvas);
    state.canvas.getBoundingClientRect = () => rect(0, 0, 500, 500);
    state.invalidate.mockClear();
    state.tabs = [];
  });

  afterEach(() => {
    cleanup();
  });

  it('stays false when the host has no readable surface', () => {
    const { result } = renderHook(() => useDomWorkPlane(makeTab()));
    expect(result.current).toBe(false);
    expect(state.invalidate).not.toHaveBeenCalled();
  });

  it('becomes true and invalidates when a visible surface matches the tab id', () => {
    mountSurface('t1');
    const { result } = renderHook(() => useDomWorkPlane(makeTab()));
    expect(result.current).toBe(true);
    expect(state.invalidate).toHaveBeenCalledTimes(1);
  });

  it('ignores a surface owned by a different workspace id', () => {
    mountSurface('other');
    const { result } = renderHook(() => useDomWorkPlane(makeTab()));
    expect(result.current).toBe(false);
  });

  it('ignores a surface that is hidden or has no size', () => {
    const hidden = mountSurface('t1');
    hidden.style.display = 'none';
    const { result } = renderHook(() => useDomWorkPlane(makeTab()));
    expect(result.current).toBe(false);

    hidden.style.display = '';
    hidden.getBoundingClientRect = () => rect(10, 10, 0, 0);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toBe(false);
  });

  it('does not delegate non-content tabs that are not conversation approvals', () => {
    mountSurface('t1');
    const { result } = renderHook(() => useDomWorkPlane(makeTab({ kind: 'approval' })));
    expect(result.current).toBe(false);
  });

  it('drops ownership when the surface disappears and the tab is live', () => {
    const surface = mountSurface('t1');
    state.tabs = [{ id: 't1', lifecycle: 'live' }];
    const { result } = renderHook(() => useDomWorkPlane(makeTab()));
    expect(result.current).toBe(true);

    surface.remove();
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toBe(false);
  });

  it('keeps ownership while the tab is retracting even if the surface is gone', () => {
    const surface = mountSurface('t1');
    const { result } = renderHook(() => useDomWorkPlane(makeTab()));
    expect(result.current).toBe(true);

    state.tabs = [{ id: 't1', lifecycle: 'retracting' }];
    surface.remove();
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toBe(true);
  });
});
