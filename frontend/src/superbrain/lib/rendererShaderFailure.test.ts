import type { WebGLRenderer } from 'three';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { installRendererShaderFailure } from './rendererShaderFailure';

type ShaderError = NonNullable<WebGLRenderer['debug']['onShaderError']>;
type ShaderErrorArgs = Parameters<ShaderError>;

afterEach(() => {
  vi.restoreAllMocks();
});

describe('installRendererShaderFailure', () => {
  it('calls the previous reporter and notifies only once, then restores it', () => {
    const previous = vi.fn();
    const onFailure = vi.fn();
    const renderer = {
      debug: { onShaderError: previous },
    } as unknown as Pick<WebGLRenderer, 'debug'>;
    const args = [{}, {}, {}, {}] as unknown as ShaderErrorArgs;

    const dispose = installRendererShaderFailure(renderer, onFailure);
    const handle = renderer.debug.onShaderError as ShaderError;

    handle(...args);
    handle(...args);

    expect(previous).toHaveBeenCalledTimes(1);
    expect(previous).toHaveBeenCalledWith(...args);
    expect(onFailure).toHaveBeenCalledTimes(1);

    dispose();
    expect(renderer.debug.onShaderError).toBe(previous);
    handle(...args);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });

  it('reports compiler diagnostics when there is no previous reporter', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const onFailure = vi.fn();
    const renderer = {
      debug: { onShaderError: null },
    } as unknown as Pick<WebGLRenderer, 'debug'>;
    const program = {};
    const vertex = {};
    const fragment = {};
    const gl = {
      getProgramInfoLog: vi.fn().mockReturnValue('program log'),
      getShaderInfoLog: vi.fn()
        .mockReturnValueOnce('vertex log')
        .mockReturnValueOnce('fragment log'),
    };
    const args = [gl, program, vertex, fragment] as unknown as ShaderErrorArgs;

    const dispose = installRendererShaderFailure(renderer, onFailure);
    (renderer.debug.onShaderError as ShaderError)(...args);

    expect(gl.getProgramInfoLog).toHaveBeenCalledWith(program);
    expect(gl.getShaderInfoLog).toHaveBeenNthCalledWith(1, vertex);
    expect(gl.getShaderInfoLog).toHaveBeenNthCalledWith(2, fragment);
    expect(error).toHaveBeenCalledWith('GAGOS visual renderer shader link failed.', {
      program: 'program log',
      vertex: 'vertex log',
      fragment: 'fragment log',
    });
    expect(onFailure).toHaveBeenCalledTimes(1);
    dispose();
  });

  it('notifies even if the previous reporter throws and preserves a replacement on disposal', () => {
    const failure = new Error('reporter failed');
    const previous = vi.fn(() => {
      throw failure;
    });
    const onFailure = vi.fn();
    const renderer = {
      debug: { onShaderError: previous },
    } as unknown as Pick<WebGLRenderer, 'debug'>;
    const args = [{}, {}, {}, {}] as unknown as ShaderErrorArgs;

    const dispose = installRendererShaderFailure(renderer, onFailure);
    const handle = renderer.debug.onShaderError as ShaderError;

    expect(() => handle(...args)).toThrow(failure);
    expect(onFailure).toHaveBeenCalledTimes(1);

    const replacement = vi.fn();
    renderer.debug.onShaderError = replacement;
    dispose();

    expect(renderer.debug.onShaderError).toBe(replacement);
    handle(...args);
    expect(previous).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });
});
