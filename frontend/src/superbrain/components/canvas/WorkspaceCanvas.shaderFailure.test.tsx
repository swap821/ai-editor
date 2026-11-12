import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { WebGLRenderer } from 'three';

// Driver boundary only: not a native compiler or full operational-root test.
const driver = vi.hoisted(() => ({ renderers: [] as WebGLRenderer[], frames: [] as Array<(state: { gl: WebGLRenderer }) => void>, previous: null as WebGLRenderer['debug']['onShaderError'], delayedCleanup: false, cleanups: [] as Array<() => void>, failRender: false }));
vi.mock('@react-three/fiber', async () => {
  const React = await import('react');
  const { createRoot } = await import('react-dom/client');
  return {
    Canvas: ({ children, onCreated }: { children: ReactNode; onCreated: (state: { gl: WebGLRenderer }) => void }) => {
      if (driver.failRender) throw new Error('controlled scene render failure');
      const canvas = React.useRef<HTMLCanvasElement>(null);
      const content = React.Children.toArray(children).filter(child => !React.isValidElement(child) || !['color', 'fog'].includes(String(child.type)));
      const initial = React.useRef({ content, onCreated });
      React.useLayoutEffect(() => {
        const gl = { domElement: canvas.current, capabilities: { isWebGL2: true }, debug: { checkShaderErrors: true, onShaderError: driver.previous } } as unknown as WebGLRenderer;
        driver.renderers.push(gl); initial.current.onCreated({ gl });
        if (driver.delayedCleanup) {
          // Controlled external-renderer lifetime: installed R3F retires its
          // separate reconciler root later than its outer DOM canvas owner.
          const detachedRoot = createRoot(document.createElement('div'));
          detachedRoot.render(<>{initial.current.content}</>);
          return () => { driver.cleanups.push(() => detachedRoot.unmount()); };
        }
      }, []);
      return <div><canvas ref={canvas} />{driver.delayedCleanup ? null : content}</div>;
    },
    useFrame: (callback: (state: { gl: WebGLRenderer }) => void) => { driver.frames.push(callback); },
  };
});
vi.mock('@/components/QualityTierProvider', async () => {
  const React = await import('react');
  return { QualityTierBoundary: ({ children }: { children: ReactNode }) => <React.Fragment>{children}</React.Fragment>,
    useQualityTier: () => ({ tier: 'low', perfTier: 'low', preference: 'auto', autoProfile: { dpr: 1 } }) };
});
vi.mock('../../core/CortexEngine', () => ({ default: () => null }));
vi.mock('./TierGovernor', () => ({ default: () => null }));
vi.mock('./RenderFrameLoop', () => ({ default: () => null }));
vi.mock('../../core/Performance/FeatureGate', () => ({ useFeatureGate: () => false }));
vi.mock('@/lib/aiosAdapter', () => ({ startAiosPolling: () => () => {} }));
vi.mock('@/lib/cognitionBus', () => ({ subscribeCognition: () => () => {} }));
vi.mock('@/lib/lifecycleStateMachine', () => ({ notifyDirective: () => {}, tickLifecycle: () => {} }));

import WorkspaceCanvas from './WorkspaceCanvas';
import { installRendererShaderFailure } from '../../lib/rendererShaderFailure';

beforeEach(() => {
  driver.renderers.length = 0; driver.frames.length = 0;
  driver.previous = null;
  driver.delayedCleanup = false; driver.cleanups.length = 0; driver.failRender = false;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as WebGLRenderingContext);
});
afterEach(() => { cleanup(); act(() => driver.cleanups.splice(0).forEach(dispose => dispose())); vi.useRealTimers(); vi.restoreAllMocks(); });

type ShaderErrorArgs = Parameters<NonNullable<WebGLRenderer['debug']['onShaderError']>>;
const linkFailure = (): ShaderErrorArgs => [{} as ShaderErrorArgs[0], {} as ShaderErrorArgs[1], {} as ShaderErrorArgs[2], {} as ShaderErrorArgs[3]];

it('retains the program and both compiler reports once, without reading retired driver objects', () => {
  const report = vi.spyOn(console, 'error').mockImplementation(() => {});
  const program = {} as ShaderErrorArgs[1];
  const vertex = {} as ShaderErrorArgs[2];
  const fragment = {} as ShaderErrorArgs[3];
  const queries: unknown[] = [];
  const context = {
    getProgramInfoLog: (target: unknown) => { queries.push(target); return 'Program link: fragment compilation failed'; },
    getShaderInfoLog: (target: unknown) => {
      queries.push(target);
      if (target === vertex) return 'Vertex: precision warning';
      if (target === fragment) return 'ERROR: 0:17: undeclared identifier';
      throw new Error('unknown shader object');
    },
  } as unknown as ShaderErrorArgs[0];
  const renderer = { debug: { checkShaderErrors: true, onShaderError: null } } as Pick<WebGLRenderer, 'debug'>;
  const onFailure = vi.fn();
  const dispose = installRendererShaderFailure(renderer, onFailure);
  const callback = renderer.debug.onShaderError!;
  callback(context, program, vertex, fragment);
  expect(report).toHaveBeenCalledTimes(1);
  expect(report.mock.calls[0][1]).toEqual({
    program: 'Program link: fragment compilation failed',
    vertex: 'Vertex: precision warning',
    fragment: 'ERROR: 0:17: undeclared identifier',
  });
  expect(queries).toEqual([program, vertex, fragment]);
  expect(onFailure).toHaveBeenCalledTimes(1);
  callback(context, program, vertex, fragment);
  dispose();
  callback(context, program, vertex, fragment);
  expect(queries).toHaveLength(3);
  expect(report).toHaveBeenCalledTimes(1);
  expect(onFailure).toHaveBeenCalledTimes(1);
  expect(renderer.debug.onShaderError).toBeNull();
});

function shaderError(gl: WebGLRenderer) {
  const callback = gl.debug.onShaderError;
  expect(callback).toBeTypeOf('function');
  act(() => callback!(...linkFailure()));
  return callback!;
}

it('still notifies failure once when a lost driver cannot supply diagnostics', () => {
  const report = vi.spyOn(console, 'error').mockImplementation(() => {});
  const renderer = { debug: { checkShaderErrors: true, onShaderError: null } } as Pick<WebGLRenderer, 'debug'>;
  const onFailure = vi.fn();
  const dispose = installRendererShaderFailure(renderer, onFailure);
  const callback = renderer.debug.onShaderError!;
  const args = linkFailure();
  args[0] = { getProgramInfoLog: () => { throw new Error('driver diagnostics unavailable'); } } as unknown as ShaderErrorArgs[0];
  expect(() => callback(...args)).not.toThrow();
  expect(onFailure).toHaveBeenCalledTimes(1);
  expect(report).toHaveBeenCalledTimes(1);
  expect(report.mock.calls[0][0]).toMatch(/diagnostics unavailable/i);
  dispose();
  callback(...args);
  expect(onFailure).toHaveBeenCalledTimes(1);
  expect(renderer.debug.onShaderError).toBeNull();
});

it('exposes existing visual fallback for a shader-link failure, then retries only the canvas', () => {
  render(<WorkspaceCanvas />);
  const gl = driver.renderers[0];
  const retired = shaderError(gl);
  expect(screen.getByText('GAGOS is still here')).toBeInTheDocument();
  const retry = screen.getByRole('button', { name: 'Retry 3D presence' });
  act(() => retired(...linkFailure()));
  expect(screen.getAllByRole('button', { name: 'Retry 3D presence' })).toHaveLength(1);
  fireEvent.click(retry);
  expect(driver.renderers).toHaveLength(2);
  expect(screen.queryByText('GAGOS is still here')).not.toBeInTheDocument();
  act(() => retired(...linkFailure()));
  expect(screen.queryByText('GAGOS is still here')).not.toBeInTheDocument();
  expect(driver.renderers[1].debug.checkShaderErrors).toBe(true);
});

it('does not announce a queued first 3D frame after its renderer failed; healthy retry can announce', () => {
  const queue: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { queue.push(callback); return queue.length; });
  const ready = vi.fn(); window.addEventListener('gagos:ready', ready);
  try {
    render(<WorkspaceCanvas />);
    act(() => driver.frames[driver.frames.length - 1]({ gl: driver.renderers[0] }));
    shaderError(driver.renderers[0]);
    act(() => queue.splice(0).forEach(callback => callback(16)));
    expect(ready).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry 3D presence' }));
    act(() => driver.frames[driver.frames.length - 1]({ gl: driver.renderers[1] }));
    act(() => queue.splice(0).forEach(callback => callback(32)));
    expect(ready).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener('gagos:ready', ready); }
});

it('releases the shader callback on unmount and rejects an already queued ready frame', () => {
  const queue: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { queue.push(callback); return queue.length; });
  const ready = vi.fn(); window.addEventListener('gagos:ready', ready);
  try {
    const app = render(<WorkspaceCanvas />);
    const gl = driver.renderers[0];
    expect(gl.debug.onShaderError).toBeTypeOf('function');
    act(() => driver.frames[driver.frames.length - 1]({ gl }));
    app.unmount();
    expect(gl.debug.onShaderError).toBeNull();
    act(() => queue.splice(0).forEach(callback => callback(16)));
    expect(ready).not.toHaveBeenCalled();
  } finally { window.removeEventListener('gagos:ready', ready); }
});

it('preserves a prior custom reporter and restores only its own renderer binding', () => {
  const reports: unknown[][] = [];
  driver.previous = (...args) => { reports.push(args); };
  const app = render(<WorkspaceCanvas />);
  const gl = driver.renderers[0];
  shaderError(gl);
  expect(reports).toHaveLength(1);
  expect(gl.debug.onShaderError).toBe(driver.previous);
  fireEvent.click(screen.getByRole('button', { name: 'Retry 3D presence' }));
  const next = driver.renderers[1];
  const laterReporter = () => {};
  next.debug.onShaderError = laterReporter;
  app.unmount();
  expect(next.debug.onShaderError).toBe(laterReporter);
});

it('retires old context notifications while the replacement retains its own restore grace', () => {
  vi.useFakeTimers();
  render(<WorkspaceCanvas />);
  const old = driver.renderers[0];
  shaderError(old);
  fireEvent.click(screen.getByRole('button', { name: 'Retry 3D presence' }));
  const retiredLoss = new Event('webglcontextlost', { cancelable: true });
  act(() => old.domElement.dispatchEvent(retiredLoss));
  expect(retiredLoss.defaultPrevented).toBe(false);
  act(() => vi.advanceTimersByTime(4000));
  expect(driver.renderers).toHaveLength(2);
  const currentLoss = new Event('webglcontextlost', { cancelable: true });
  act(() => driver.renderers[1].domElement.dispatchEvent(currentLoss));
  expect(currentLoss.defaultPrevented).toBe(true);
  act(() => vi.advanceTimersByTime(3999));
  expect(driver.renderers).toHaveLength(2);
  act(() => vi.advanceTimersByTime(1));
  expect(driver.renderers).toHaveLength(3);
});

it('does not revive a retired ready signal when Retry precedes separate-root cleanup', () => {
  driver.delayedCleanup = true;
  const queue: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { queue.push(callback); return queue.length; });
  const ready = vi.fn(); window.addEventListener('gagos:ready', ready);
  try {
    render(<WorkspaceCanvas />);
    act(() => driver.frames[0]({ gl: driver.renderers[0] }));
    shaderError(driver.renderers[0]);
    expect(driver.cleanups).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Retry 3D presence' }));
    expect(driver.renderers).toHaveLength(2);
    act(() => queue.splice(0).forEach(callback => callback(16)));
    expect(ready).not.toHaveBeenCalled();
    act(() => driver.frames[driver.frames.length - 1]({ gl: driver.renderers[1] }));
    act(() => queue.splice(0).forEach(callback => callback(32)));
    expect(ready).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener('gagos:ready', ready); }
});

it('retires readiness when the actual visual error boundary catches a renderer failure', () => {
  driver.delayedCleanup = true;
  const queue: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { queue.push(callback); return queue.length; });
  const ready = vi.fn(); window.addEventListener('gagos:ready', ready);
  try {
    const app = render(<WorkspaceCanvas />);
    const gl = driver.renderers[0];
    const retiredShaderCallback = gl.debug.onShaderError!;
    act(() => driver.frames[0]({ gl }));
    driver.failRender = true;
    app.rerender(<WorkspaceCanvas />);
    expect(screen.getByText('GAGOS is still here')).toBeInTheDocument();
    expect(driver.cleanups).toHaveLength(1);
    act(() => queue.splice(0).forEach(callback => callback(16)));
    expect(ready).not.toHaveBeenCalled();
    expect(gl.debug.onShaderError).toBeNull();
    driver.failRender = false;
    fireEvent.click(screen.getByRole('button', { name: 'Retry 3D presence' }));
    expect(driver.renderers).toHaveLength(2);
    act(() => retiredShaderCallback(...linkFailure()));
    expect(screen.queryByText('GAGOS is still here')).not.toBeInTheDocument();
    act(() => driver.frames[driver.frames.length - 1]({ gl: driver.renderers[1] }));
    act(() => queue.splice(0).forEach(callback => callback(32)));
    expect(ready).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener('gagos:ready', ready); }
});
