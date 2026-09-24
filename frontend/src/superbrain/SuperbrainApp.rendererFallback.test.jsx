import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SuperbrainApp from './SuperbrainApp';
import { setRendererFallbackPresentation } from '../livingMirror/rendererFallbackPresentation';

const rendererFailureState = vi.hoisted(() => ({ value: false }));
const contextTrackerState = vi.hoisted(() => ({ lost: vi.fn(), restored: vi.fn() }));
const originalVisualViewport = Object.getOwnPropertyDescriptor(window, 'visualViewport');
const originalInnerHeight = Object.getOwnPropertyDescriptor(window, 'innerHeight');

function restoreWindowDescriptor(name, descriptor) {
  if (descriptor) Object.defineProperty(window, name, descriptor);
  else delete window[name];
}

function installVisualViewport({ height, offsetTop = 0, scale = 1 }) {
  const viewport = new EventTarget();
  Object.assign(viewport, { height, offsetTop, scale });
  Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
  return viewport;
}

vi.mock('@/components/ui/BootSequence', () => ({
  default: () => null,
}));

vi.mock('@/components/canvas/WorkspaceCanvas', () => ({
  default: ({ children }) => {
    if (rendererFailureState.value) throw new Error('renderer subtree failed');
    return <div className="scene-layer"><canvas aria-hidden="true" />{children}</div>;
  },
}));

vi.mock('../workbench/GagosChrome', () => ({
  default: () => <div data-testid="gagos-chrome" />,
}));

vi.mock('../workbench/SuperbrainReactiveEffects', () => ({
  default: () => null,
}));

vi.mock('../livingMirror/LivingWorkspaceShell', () => ({
  LivingWorkspaceShell: () => null,
}));

vi.mock('../livingMirror/experienceMode', () => ({
  readExperienceMode: () => 'beginner',
  writeExperienceMode: vi.fn(),
}));

vi.mock('../livingMirror/being/useBeingPresentation', () => ({
  useBeingPresentation: () => ({
    phase: 'resting',
    taskState: 'idle',
    coherence: 'fresh',
    motion: 'calm',
    attention: 'none',
    signals: [],
    workers: [],
  }),
}));

vi.mock('../livingMirror/being/presentationFromStores', () => ({
  beingStatusText: () => 'GAGOS is ready.',
}));

vi.mock('../livingMirror/observability/contextRecovery', () => ({
  createContextRecoveryTracker: () => ({
    handleLost: contextTrackerState.lost,
    handleRestored: contextTrackerState.restored,
  }),
}));

vi.mock('../livingMirror/observability/frontendMetrics', () => ({
  createMirrorReconnectTracker: () => () => {},
  recordFrontendMetric: vi.fn(),
  startFrameTimeSampler: () => () => {},
}));

vi.mock('./lib/aiosMirror', () => ({
  startMirrorClient: vi.fn(async () => {}),
  stopMirrorClient: vi.fn(),
}));

vi.mock('./lib/tabStore', () => ({
  useTabStore: () => ({ panels: [], tabs: [], focusId: null, attention: null }),
}));

vi.mock('./lib/mirrorStore', () => ({
  useMirrorStore: Object.assign(
    () => ({ connection: 'disconnected' }),
    { subscribe: () => () => {} },
  ),
}));

describe('SuperbrainApp renderer fallback bridge', () => {
  afterEach(() => {
    rendererFailureState.value = false;
    contextTrackerState.lost.mockClear();
    contextTrackerState.restored.mockClear();
    vi.restoreAllMocks();
    setRendererFallbackPresentation(false);
    document.body.innerHTML = '';
    restoreWindowDescriptor('visualViewport', originalVisualViewport);
    restoreWindowDescriptor('innerHeight', originalInnerHeight);
  });

  it('keeps the app composer within the visible viewport while a text field is focused', async () => {
    const viewport = installVisualViewport({ height: 300 });
    render(<SuperbrainApp />);
    const app = document.querySelector('.lm-app');
    if (!app) throw new Error('Expected the GAGOS app root to mount.');

    const chat = document.createElement('section');
    chat.className = 'gagos-chat';
    const input = document.createElement('input');
    input.type = 'text';
    chat.append(input);
    app.append(chat);
    input.focus();

    await waitFor(() => expect(app).toHaveAttribute('data-keyboard-open', 'true'));
    expect(app.style.getPropertyValue('--lm-keyboard-inset')).toBe('500px');
    expect(app.style.getPropertyValue('--lm-visible-viewport-height')).toBe('300px');

    viewport.height = 420;
    viewport.offsetTop = 10;
    viewport.dispatchEvent(new Event('resize'));
    await waitFor(() => expect(app.style.getPropertyValue('--lm-keyboard-inset')).toBe('370px'));

    input.blur();
    await waitFor(() => expect(app).not.toHaveAttribute('data-keyboard-open', 'true'));
    expect(app.style.getPropertyValue('--lm-keyboard-inset')).toBe('');
    expect(app.style.getPropertyValue('--lm-visible-viewport-height')).toBe('');
  });

  it('measures keyboard occlusion from the app bounds when its minimum height exceeds the viewport', async () => {
    const viewport = installVisualViewport({ height: 180 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 390 });
    render(<SuperbrainApp />);
    const app = document.querySelector('.lm-app');
    if (!app) throw new Error('Expected the GAGOS app root to mount.');
    app.getBoundingClientRect = () => ({ bottom: 520, height: 520 });

    const chat = document.createElement('section');
    chat.className = 'gagos-chat';
    const input = document.createElement('input');
    input.type = 'text';
    chat.append(input);
    app.append(chat);
    input.focus();

    await waitFor(() => expect(app).toHaveAttribute('data-keyboard-open', 'true'));
    expect(app.style.getPropertyValue('--lm-keyboard-inset')).toBe('340px');
    expect(viewport.height).toBe(180);
  });

  it('does not move the composer for non-text focus or pinch zoom', async () => {
    const viewport = installVisualViewport({ height: 300 });
    render(<SuperbrainApp />);
    const app = document.querySelector('.lm-app');
    if (!app) throw new Error('Expected the GAGOS app root to mount.');

    const chat = document.createElement('section');
    chat.className = 'gagos-chat';
    const button = document.createElement('button');
    chat.append(button);
    app.append(chat);
    button.focus();
    viewport.dispatchEvent(new Event('resize'));
    await waitFor(() => expect(app).not.toHaveAttribute('data-keyboard-open', 'true'));

    const input = document.createElement('input');
    input.type = 'text';
    button.replaceWith(input);
    input.focus();
    viewport.scale = 1.5;
    viewport.dispatchEvent(new Event('resize'));
    await waitFor(() => expect(app).not.toHaveAttribute('data-keyboard-open', 'true'));
  });

  it('projects the managed fallback into the human-facing shell and clears after recovery', async () => {
    render(<SuperbrainApp />);

    expect(screen.queryByTestId('renderer-fallback-notice')).not.toBeInTheDocument();

    const fallback = document.createElement('div');
    fallback.className = 'webgl-fallback';
    document.body.append(fallback);

    await waitFor(() => expect(screen.getByTestId('renderer-fallback-notice')).toBeInTheDocument());
    expect(screen.getByTestId('renderer-fallback-notice')).toHaveTextContent('GAGOS controls are still working.');

    fallback.remove();
    await waitFor(() => expect(screen.queryByTestId('renderer-fallback-notice')).not.toBeInTheDocument());
  });

  it('keeps the conversation shell mounted when the renderer subtree throws', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    rendererFailureState.value = true;

    render(<SuperbrainApp />);

    await waitFor(() => expect(screen.getByTestId('renderer-fallback-notice')).toBeInTheDocument());
    expect(screen.getByTestId('gagos-chrome')).toBeInTheDocument();
    expect(screen.getByText('GAGOS controls are still working.')).toBeInTheDocument();
  });

  it('shows the product fallback while a measured WebGL context is lost and clears after restoration', async () => {
    render(<SuperbrainApp />);

    await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toBeInTheDocument());
    const canvas = document.querySelector('.scene-layer canvas');
    if (!canvas) throw new Error('Expected the managed scene canvas to mount.');

    fireEvent(canvas, new Event('webglcontextlost', { cancelable: true }));
    expect(contextTrackerState.lost).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.getByTestId('renderer-fallback-notice')).toBeInTheDocument());
    expect(screen.getByTestId('renderer-fallback-notice')).toHaveTextContent('Visual organism unavailable.');

    fireEvent(canvas, new Event('webglcontextrestored'));
    await waitFor(() => expect(screen.queryByTestId('renderer-fallback-notice')).not.toBeInTheDocument());
  });

  it('removes a lost canvas before retrying a fresh renderer while keeping the shell mounted', async () => {
    render(<SuperbrainApp />);

    await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toBeInTheDocument());
    const canvas = document.querySelector('.scene-layer canvas');
    if (!canvas) throw new Error('Expected the managed scene canvas to mount.');

    fireEvent(canvas, new Event('webglcontextlost', { cancelable: true }));
    await waitFor(() => expect(screen.getByTestId('renderer-fallback-notice')).toBeInTheDocument());
    expect(document.querySelector('.scene-layer canvas')).not.toBeInTheDocument();
    expect(screen.getByTestId('gagos-chrome')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry visual organism' }));

    await waitFor(() => expect(document.querySelector('.scene-layer canvas')).toBeInTheDocument());
    expect(screen.getByTestId('gagos-chrome')).toBeInTheDocument();
  });
});
