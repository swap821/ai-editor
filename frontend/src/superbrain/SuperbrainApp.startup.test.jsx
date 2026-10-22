import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { createFixtureJourneyTransport } from '../livingMirror/being/fixtureJourneyTransport';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

// A rejected renderer dependency must be caught below the DOM application,
// not prevent its module from evaluating. Keep the real shell, conversation,
// stores, permission and Stop owners; only the external renderer is faulted.
const rendererFault = vi.hoisted(() => {
  let reject;
  let entered;
  const started = new Promise(resolve => { entered = resolve; });
  const blocked = new Promise((_, fail) => { reject = fail; });
  return { started, blocked, reject, entered };
});
vi.mock('three', async () => {
  rendererFault.entered();
  await rendererFault.blocked;
  throw new Error('Unreachable renderer module');
});
const observed = vi.hoisted(() => ({ root: null, loader: null, navigationErrors: [] }));
const recordNavigationError = error => {
  if (/not implemented.*navigation/i.test(error.message)) observed.navigationErrors.push(error.message);
};
vi.mock('react-dom/client', async importOriginal => {
  const actual = await importOriginal();
  return { ...actual, createRoot(...args) {
    const root = actual.createRoot(...args); observed.root = root; return root;
  } };
});
const fixture = createFixtureJourneyTransport({ origin: window.location.origin, assetFetch: vi.fn() });
vi.stubGlobal('fetch', fixture.fetch);
vi.stubGlobal('EventSource', fixture.EventSource);
vi.stubGlobal('matchMedia', query => Object.assign(new EventTarget(), {
  matches: query.includes('reduced-motion'), media: query,
  addListener() {}, removeListener() {},
}));
// Module evaluation is the boundary being tested. Keep its cold transform
// outside the unchanged per-interaction test budget, not a longer timeout.
let loadFailure;
beforeAll(async () => {
  globalThis.jsdom.virtualConsole.on('jsdomError', recordNavigationError);
  document.body.innerHTML = '<div id="boot-loader"><span class="boot-label">Starting</span></div><div id="root"></div>';
  observed.loader = document.getElementById('boot-loader');
  runInNewContext(readFileSync('public/boot-loader.js', 'utf8'), { window, document });
  vi.spyOn(console, 'error').mockImplementation(() => {});
  await act(async () => {
    try { await import('../main'); }
    catch (error) { loadFailure = error; }
  });
  // Wait for the fault boundary, not every import: the renderer intentionally
  // remains unresolved until after the person has typed into the real DOM.
  await rendererFault.started;
});
afterEach(async () => {
  await act(async () => { observed.root?.unmount(); });
  globalThis.jsdom.virtualConsole.removeListener('jsdomError', recordNavigationError);
  cleanup(); fixture?.dispose(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  localStorage.clear();
});

it('keeps the real composer and Stop available when a renderer dependency cannot load', async () => {
  localStorage.setItem('gagos-experience-mode', 'beginner');
  expect(loadFailure, 'The DOM application must not evaluate the failed renderer dependency').toBeUndefined();
  const input = await screen.findByRole('textbox', { name: 'Talk to GAGOS' });
  await waitFor(() => expect(observed.loader).toHaveAttribute('data-done', '1'));
  expect(observed.loader.querySelector('.boot-label')).not.toHaveTextContent('The voyaging mind is ready');
  // Real request/reader/decision owners stay active even before any renderer.
  // Every response and decision here is the isolated in-memory transport.
  fireEvent.change(input, { target: { value: 'Create a greeting example' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(fixture.getSnapshot().pending).toBe(true));
  await act(async () => { fixture.advance(); fixture.advance(); });
  const { getPendingApproval } = await import('./lib/aiosAdapter');
  await waitFor(() => expect(getPendingApproval()?.token).toMatch(/^fixture-/));
  const requestToken = getPendingApproval().token;
  fireEvent.change(input, { target: { value: 'Unsent through renderer failure.' } });
  expect(screen.getByRole('button', { name: 'Emergency stop' })).toBeEnabled();
  await act(async () => {
    rendererFault.reject(new Error('Renderer dependency deliberately unavailable'));
    await vi.dynamicImportSettled();
  });
  await waitFor(() => expect(screen.getByText('Visual organism unavailable.')).toBeVisible());
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toBe(input);
  expect(input).toHaveValue('Unsent through renderer failure.');
  expect(screen.getByRole('button', { name: 'Emergency stop' })).toBeEnabled();
  observed.navigationErrors.length = 0;
  fireEvent.click(screen.getByRole('button', { name: 'Retry visual organism' }));
  expect(screen.getByText('Loading the organism. Operational controls remain available.')).toBeVisible();
  await act(async () => { await vi.dynamicImportSettled(); });
  // jsdom does not perform navigation: observe its actual reload diagnostic
  // rather than letting that no-op falsely prove browser draft retention.
  expect(observed.navigationErrors).toEqual([]);
  expect(screen.getByText('Visual organism unavailable.')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toBe(input);
  expect(input).toHaveValue('Unsent through renderer failure.');
  expect(getPendingApproval()?.token).toBe(requestToken);
  expect(document.querySelectorAll('canvas').length).toBeLessThanOrEqual(1);
});
