import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { SceneReadinessNotice } from './SceneReadinessNotice';

function makeStage({ canvas = true, fallback = false } = {}) {
  const stage = document.createElement('div');
  document.body.appendChild(stage);
  let canvasEl: HTMLCanvasElement | null = null;
  if (canvas) {
    const layer = document.createElement('div');
    layer.className = 'scene-layer';
    canvasEl = document.createElement('canvas');
    layer.appendChild(canvasEl);
    stage.appendChild(layer);
  }
  if (fallback) {
    const fb = document.createElement('div');
    fb.className = 'webgl-fallback';
    stage.appendChild(fb);
  }
  return { stage, canvasEl, ref: { current: stage } };
}

function signalReady(canvas: unknown) {
  act(() => {
    window.dispatchEvent(new CustomEvent('gagos:ready', { detail: { canvas } }));
  });
}

const statusQuery = { name: 'Visual organism loading' };

afterEach(() => {
  cleanup();
  document.body.innerHTML = '';
});

describe('SceneReadinessNotice', () => {
  it('shows the loading status and portals the cue into the host while pending', () => {
    const { ref } = makeStage();
    const host = document.createElement('div');
    document.body.appendChild(host);

    render(<SceneReadinessNotice host={host} stageRef={ref} />);

    expect(screen.getByRole('status', statusQuery).textContent).toBe(
      'Loading the organism. Operational controls remain available.',
    );
    const cue = host.querySelector('.lm-scene-loading');
    expect(cue?.textContent).toBe('Preparing the visual organism…');
    expect(cue?.getAttribute('aria-hidden')).toBe('true');
  });

  it('still shows the status when there is no host element', () => {
    const { ref } = makeStage();
    const { container } = render(<SceneReadinessNotice host={null} stageRef={ref} />);

    expect(screen.getByRole('status', statusQuery)).toBeTruthy();
    expect(container.querySelector('.lm-scene-loading')).toBeNull();
    expect(document.querySelector('.lm-scene-loading')).toBeNull();
  });

  it('hides the notice when the current canvas reports ready', () => {
    const { ref, canvasEl } = makeStage();
    const host = document.createElement('div');
    document.body.appendChild(host);
    render(<SceneReadinessNotice host={host} stageRef={ref} />);

    signalReady(canvasEl);

    expect(screen.queryByRole('status', statusQuery)).toBeNull();
    expect(host.querySelector('.lm-scene-loading')).toBeNull();
  });

  it('ignores ready events from a canvas that is not the stage canvas or has no canvas', () => {
    const { ref } = makeStage();
    render(<SceneReadinessNotice host={null} stageRef={ref} />);

    signalReady(document.createElement('canvas'));
    signalReady(undefined);
    signalReady({});

    expect(screen.getByRole('status', statusQuery)).toBeTruthy();
  });

  it('renders nothing when the WebGL fallback is present, even after a ready event', () => {
    const { ref, canvasEl } = makeStage({ fallback: true });
    const { container } = render(<SceneReadinessNotice host={null} stageRef={ref} />);

    expect(container.textContent).toBe('');

    signalReady(canvasEl);
    expect(screen.queryByRole('status', statusQuery)).toBeNull();
  });

  it('returns to pending when the ready canvas is replaced', async () => {
    const { ref, stage, canvasEl } = makeStage();
    render(<SceneReadinessNotice host={null} stageRef={ref} />);
    signalReady(canvasEl);
    expect(screen.queryByRole('status', statusQuery)).toBeNull();

    const replacement = document.createElement('canvas');
    canvasEl?.replaceWith(replacement);

    expect(await screen.findByRole('status', statusQuery)).toBeTruthy();

    signalReady(replacement);
    expect(screen.queryByRole('status', statusQuery)).toBeNull();
    expect(stage.contains(replacement)).toBe(true);
  });

  it('shows the fallback state instead of the notice when the fallback appears later', async () => {
    const { ref, stage } = makeStage();
    const { container } = render(<SceneReadinessNotice host={null} stageRef={ref} />);
    expect(screen.getByRole('status', statusQuery)).toBeTruthy();

    const fb = document.createElement('div');
    fb.className = 'webgl-fallback';
    stage.appendChild(fb);

    await act(async () => {
      await Promise.resolve();
    });
    expect(container.textContent).toBe('');
  });
});
