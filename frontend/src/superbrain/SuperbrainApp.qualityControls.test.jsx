import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SuperbrainApp from './SuperbrainApp';
import { MirrorConnectionNotice } from '../livingMirror/MirrorConnectionNotice';
import { setRendererFallbackPresentation } from '../livingMirror/rendererFallbackPresentation';

vi.mock('@/components/ui/BootSequence', () => ({ default: () => null }));
// DOM failure harness qualifies owner/lifetime wiring, not R3F/GPU rendering.
// The installed Canvas and actual point-field witness is a separate test.
vi.mock('@/components/canvas/WorkspaceCanvas', async () => {
  const { useQualityTier } = await import('./components/QualityTierProvider');
  return { default: function Scene() {
    const { tier } = useQualityTier();
    return <div className="scene-layer"><canvas data-tier={tier} /></div>;
  } };
});
vi.mock('../workbench/GagosChrome', () => ({ default: () => <input aria-label="Lifetime fixture draft" /> }));
vi.mock('../workbench/SuperbrainReactiveEffects', () => ({ default: () => null }));
vi.mock('../livingMirror/being/WorkspaceConnectionOverlay', () => ({
  WorkspaceConnectionOverlay: () => null,
}));
vi.mock('../livingMirror/being/WorkspaceConnectionProjection', () => ({ WorkspaceConnectionProjection: () => null }));
vi.mock('../livingMirror/LivingWorkspaceShell', async () => {
  const { MirrorConnectionNotice: Notice } = await import('../livingMirror/MirrorConnectionNotice');
  return { LivingWorkspaceShell: ({ experienceMode }) => <Notice experienceMode={experienceMode} /> };
});
vi.mock('./lib/aiosMirror', () => ({ startMirrorClient: vi.fn(async () => {}), stopMirrorClient: vi.fn() }));
vi.mock('../livingMirror/observability/frontendMetrics', () => ({
  createMirrorReconnectTracker: () => () => {}, recordFrontendMetric: vi.fn(), startRafIntervalSampler: () => () => {},
}));

beforeEach(() => {
  localStorage.clear();
  setRendererFallbackPresentation(false);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
});
afterEach(() => {
  setRendererFallbackPresentation(false);
  vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear();
});

it.each(['beginner', 'expert'])('uses one real preference owner for %s DOM and scene, without remounting them', async (mode) => {
  localStorage.setItem('gagos-experience-mode', mode);
  localStorage.setItem('gag-quality-tier-v3', 'high'); // retain the saved-manual contract
  render(<SuperbrainApp />);
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toBeInTheDocument());
  const canvas = document.querySelector('.scene-layer canvas');
  const draft = screen.getByRole('textbox', { name: 'Lifetime fixture draft' });
  fireEvent.change(draft, { target: { value: 'Unsent, not backend work.' } });
  expect(control).toHaveValue('high');
  for (const tier of ['low', 'medium', 'high']) {
    fireEvent.change(control, { target: { value: tier } });
    expect(control).toHaveValue(tier);
    expect(canvas).toHaveAttribute('data-tier', tier);
    expect(localStorage.getItem('gag-quality-tier-v3')).toBe(tier);
    expect(document.querySelector('.scene-layer canvas')).toBe(canvas);
    expect(screen.getByRole('textbox', { name: 'Lifetime fixture draft' })).toBe(draft);
    expect(draft).toHaveValue('Unsent, not backend work.');
  }
  expect(screen.getByRole('group', { name: 'Rendering preferences' })).toHaveAttribute('aria-live', 'off');
});

it('keeps a session preference editable through measured context loss and a fresh-renderer retry when storage is blocked', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage blocked'); });
  render(<SuperbrainApp />);
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toBeInTheDocument());
  const oldCanvas = document.querySelector('.scene-layer canvas');
  fireEvent.change(control, { target: { value: 'low' } });
  expect(oldCanvas).toHaveAttribute('data-tier', 'low');
  fireEvent(oldCanvas, new Event('webglcontextlost', { cancelable: true }));
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toBeNull());
  expect(screen.getByRole('combobox', { name: 'Visual detail' })).toBe(control);
  fireEvent.change(control, { target: { value: 'medium' } });
  expect(control).toHaveValue('medium');
  fireEvent.click(screen.getByRole('button', { name: 'Retry visual organism' }));
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toHaveAttribute('data-tier', 'medium'));
  expect(document.querySelector('.scene-layer canvas')).not.toBe(oldCanvas);
  expect(localStorage.getItem('gag-quality-tier-v3')).toBeNull();
});

it('restores only a validated operator preference and discards old machine-verdict keys', async () => {
  localStorage.setItem('gag-quality-tier-v3', 'medium');
  localStorage.setItem('gag-quality-tier', 'low');
  localStorage.setItem('gag-quality-tier-v2', 'low');
  render(<SuperbrainApp />);
  expect(screen.getByRole('combobox', { name: 'Visual detail' })).toHaveValue('medium');
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toHaveAttribute('data-tier', 'medium'));
  expect(localStorage.getItem('gag-quality-tier')).toBeNull();
  expect(localStorage.getItem('gag-quality-tier-v2')).toBeNull();
});

it('does not advertise a fake selector when a standalone notice has no quality owner', () => {
  render(<MirrorConnectionNotice />);
  expect(screen.queryByRole('combobox', { name: 'Visual detail' })).not.toBeInTheDocument();
});

it('rejects malformed saved and DOM values, defaulting to Auto without storing a machine verdict', async () => {
  localStorage.setItem('gag-quality-tier-v3', 'machine-fast');
  localStorage.setItem('gag-quality-tier-v4', 'machine-verdict');
  render(<SuperbrainApp />);
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  expect(control).toHaveValue('auto');
  expect(Array.from(control.options, option => option.value)).toEqual(['auto', 'high', 'medium', 'low']);
  fireEvent.change(control, { target: { value: 'invalid' } });
  expect(control).toHaveValue('auto');
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toHaveAttribute('data-tier', 'high'));
  expect(localStorage.getItem('gag-quality-tier-v3')).toBe('machine-fast');
  expect(localStorage.getItem('gag-quality-tier-v4')).toBe('machine-verdict');
});

it('defaults fresh sessions to Auto and restores only explicit v4 preferences', async () => {
  render(<SuperbrainApp />);
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  expect(control).toHaveValue('auto');
  expect(localStorage.getItem('gag-quality-tier-v4')).toBeNull();
  fireEvent.change(control, { target: { value: 'medium' } });
  expect(localStorage.getItem('gag-quality-tier-v4')).toBe('medium');
  fireEvent.change(control, { target: { value: 'auto' } });
  expect(control).toHaveValue('auto');
  expect(localStorage.getItem('gag-quality-tier-v4')).toBe('auto');
  expect(localStorage.getItem('gag-quality-tier-v3')).toBe('medium');
  // Join the real lazy scene as well as checking its immediate DOM owner;
  // do not leave its Suspense completion to a later test's lifetime.
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toHaveAttribute('data-tier', 'high'));
});

it.each(['auto', 'low', 'medium', 'high'])('uses the explicit v4 %s preference ahead of an older manual choice', async preference => {
  localStorage.setItem('gag-quality-tier-v4', preference);
  localStorage.setItem('gag-quality-tier-v3', 'medium');
  render(<SuperbrainApp />);
  expect(screen.getByRole('combobox', { name: 'Visual detail' })).toHaveValue(preference);
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toHaveAttribute('data-tier', preference === 'auto' ? 'high' : preference));
  expect(localStorage.getItem('gag-quality-tier-v3')).toBe('medium');
});

it('keeps manual detail inside the existing collapsed phone disclosure', async () => {
  vi.stubGlobal('matchMedia', query => Object.assign(new EventTarget(), { matches: query.includes('max-width: 767px') }));
  render(<SuperbrainApp />);
  const details = document.querySelector('.lm-connection__details');
  expect(details).not.toHaveAttribute('open');
  // jsdom/Testing Library does not implement closed-details layout exclusion.
  // Native browser qualification separately checks hidden content and reach.
  expect(screen.getByRole('combobox', { name: 'Visual detail' }).closest('details')).toBe(details);
  details.open = true; fireEvent(details, new Event('toggle'));
  const control = await screen.findByRole('combobox', { name: 'Visual detail' });
  expect(control.closest('details')).toBe(details);
  fireEvent.change(control, { target: { value: 'low' } });
  await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toHaveAttribute('data-tier', 'low'));
});
