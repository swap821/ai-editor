import { useLayoutEffect, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';

type Props = { host: HTMLElement | null; stageRef: RefObject<HTMLDivElement | null> };
type VisualState = 'pending' | 'ready' | 'fallback';

/** A nonblocking startup cue owned by this app's current renderer canvas. */
export function SceneReadinessNotice({ host, stageRef }: Props) {
  const [state, setState] = useState<VisualState>('pending');
  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    let readyCanvas: HTMLCanvasElement | null = null;
    const currentCanvas = () => stage.querySelector<HTMLCanvasElement>('.scene-layer canvas');
    const fallback = () => stage.querySelector('.webgl-fallback');
    const sync = () => {
      if (fallback()) { readyCanvas = null; setState('fallback'); return; }
      const canvas = currentCanvas();
      setState(canvas && canvas === readyCanvas ? 'ready' : 'pending');
    };
    const ready = (event: Event) => {
      const canvas = (event as CustomEvent<{ canvas?: unknown }>).detail?.canvas;
      if (canvas instanceof HTMLCanvasElement && canvas === currentCanvas() && !fallback()) {
        readyCanvas = canvas;
        setState('ready');
      }
    };
    window.addEventListener('gagos:ready', ready);
    const observer = typeof MutationObserver === 'function' ? new MutationObserver(sync) : null;
    observer?.observe(stage, { childList: true, subtree: true });
    sync();
    return () => { observer?.disconnect(); window.removeEventListener('gagos:ready', ready); };
  }, [stageRef]);
  if (state !== 'pending') return null;
  return <>
    {host && createPortal(<p className="lm-scene-loading" aria-hidden="true">Preparing the visual organism…</p>, host)}
    <span className="lm-being-status" role="status" aria-label="Visual organism loading">Loading the organism. Operational controls remain available.</span>
  </>;
}
