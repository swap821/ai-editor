import type { WebGLRenderer } from 'three';

/** Link errors are renderer callbacks, not React exceptions. Own one notifier
 * per renderer lifetime without disabling checking or a prior custom reporter. */
export function installRendererShaderFailure(renderer: Pick<WebGLRenderer, 'debug'>, onFailure: () => void): () => void {
  const previous = renderer.debug.onShaderError;
  let active = true;
  let notified = false;
  const handle: NonNullable<WebGLRenderer['debug']['onShaderError']> = (...args) => {
    if (!active || notified) return;
    notified = true;
    try {
      if (previous) previous(...args);
      else {
        // Installing a callback replaces Three's default compiler reporting.
        // Read driver diagnostics only on this live failure path, never frames.
        const [gl, program, vertex, fragment] = args;
        try {
          console.error('GAGOS visual renderer shader link failed.', {
            program: gl.getProgramInfoLog(program),
            vertex: gl.getShaderInfoLog(vertex),
            fragment: gl.getShaderInfoLog(fragment),
          });
        } catch {
          // A lost/disposed context may no longer expose compiler diagnostics.
          console.error('GAGOS visual renderer shader link failed. Compiler diagnostics unavailable.');
        }
      }
    } finally {
      onFailure();
    }
  };
  renderer.debug.onShaderError = handle;
  return () => {
    active = false;
    if (renderer.debug.onShaderError === handle) renderer.debug.onShaderError = previous;
  };
}
