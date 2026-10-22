import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); document.body.innerHTML = ''; });
function start(controlsReady = false) {
  document.body.innerHTML = '<div id="boot-loader"><span class="boot-label">Starting</span></div>'
    + (controlsReady ? '<div class="lm-app" data-controls-ready="true"></div>' : '');
  const host = Object.assign(new window.EventTarget(), {
    setTimeout: window.setTimeout.bind(window), clearTimeout: window.clearTimeout.bind(window),
  });
  runInNewContext(readFileSync('public/boot-loader.js', 'utf8'), { window: host, document });
  return { host, loader: document.getElementById('boot-loader') };
}
it('releases the blocking loader when actual controls announce readiness, without claiming a rendered being', () => {
  const { host, loader } = start();
  expect(loader).not.toHaveAttribute('data-done');
  host.dispatchEvent(new Event('gagos:controls-ready'));
  expect(loader).toHaveAttribute('data-done', '1');
  expect(loader).not.toHaveTextContent('The voyaging mind is ready');
});
it('does not miss a controls-ready handoff that occurred before the external loader script', () => {
  const { loader } = start(true);
  expect(loader).toHaveAttribute('data-done', '1');
  expect(loader).not.toHaveTextContent('The voyaging mind is ready');
});
it('removes a stalled safety loader without inventing first-frame readiness', () => {
  const { loader } = start();
  vi.advanceTimersByTime(9000);
  expect(loader).toHaveAttribute('data-done', '1');
  expect(loader).not.toHaveTextContent('The voyaging mind is ready');
});
