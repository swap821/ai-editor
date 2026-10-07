'use client';
import { useLayoutEffect, useRef, type MutableRefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { PerspectiveCamera } from 'three';

/** One camera, two rectangles: the body keeps its authored presence pane;
 * the renderer covers the stage so its own nerves can reach the DOM controls.
 * Layout observers update a private camera adapter, not semantic body state. */
export default function PresenceViewport({ phoneFocusRef }: { phoneFocusRef?: MutableRefObject<boolean> }) {
  const camera = useThree(state => state.camera);
  const gl = useThree(state => state.gl);
  const size = useThree(state => state.size);
  const invalidate = useThree(state => state.invalidate);
  const restoreFrame = useRef<null | (() => void)>(null);

  useLayoutEffect(() => {
    const canvas = gl.domElement;
    const host = canvas?.closest('.lm-app');
    const pane = host?.querySelector('.lm-scene');
    if (!(camera instanceof PerspectiveCamera) || !pane || !canvas) return;
    const previousView = camera.view ? { ...camera.view } : null;
    const previousAspect = camera.aspect;
    let frame: { width: number; height: number; x: number; y: number; stageWidth: number; stageHeight: number } | null = null;
    const apply = () => {
      if (!frame) return;
      const view = camera.view;
      // R3F/Drei can update aspect on resize. Restore the pane projection before
      // Framing, body anchors and the compositor, without taking render ownership.
      if (!view?.enabled || camera.aspect !== frame.width / frame.height
        || view.fullWidth !== frame.width || view.fullHeight !== frame.height
        || view.offsetX !== frame.x || view.offsetY !== frame.y
        || view.width !== frame.stageWidth || view.height !== frame.stageHeight) {
        camera.setViewOffset(frame.width, frame.height, frame.x, frame.y, frame.stageWidth, frame.stageHeight);
      }
    };
    const measure = () => {
      const body = pane.getBoundingClientRect();
      const stage = canvas.getBoundingClientRect();
      if (![body.left, body.top, body.width, body.height, stage.left, stage.top, stage.width, stage.height].every(Number.isFinite)
        || body.width <= 0 || body.height <= 0 || stage.width <= 0 || stage.height <= 0) return;
      const phoneFocus = host!.getAttribute('data-being-focus') === 'true' && stage.width < 768;
      const activeFocus = host!.getAttribute('data-being-focus') === 'true'
        && host!.getAttribute('data-working') === 'true'
        && (stage.width < 768 || stage.height >= 521);
      const desktopWork = host!.getAttribute('data-working') === 'true'
        && stage.width >= 768 && stage.height >= 521;
      let left = body.left, top = body.top, width = body.width, height = body.height;
      if (desktopWork) {
        // Ordinary retained work needs the same control-free body fit as Focus.
        // Its32% marker still includes the header/mode band; use measured rows
        // rather than shifting controls or framing the crown behind them.
        const bottom = top + height;
        for (const element of host!.querySelectorAll('.lm-header, .gagos-experience-mode')) {
          const rect = element.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0 && rect.left < left + width && rect.right > left
            && rect.bottom > top && rect.top < bottom) top = Math.max(top, rect.bottom + 12);
        }
        height = bottom - top;
        if (height <= 0 || !Number.isFinite(height)) return;
      }
      if (phoneFocus && !activeFocus) {
        // Focus removes history, not human controls. Measure their actual height
        // (draft wrapping, mode, safe areas, notice expansion, keyboard), rather
        // than rendering the cortex underneath a fixed whole-screen overlay.
        left = stage.left + 12; width = stage.width - 24;
        top = stage.top + 12;
        for (const element of host!.querySelectorAll('.lm-header, .gagos-experience-mode, .lm-connection')) {
          const rect = element.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) top = Math.max(top, rect.bottom + 12);
        }
        const chat = host!.querySelector('.gagos-chat')?.getBoundingClientRect();
        // The notice/dock inherit the shell's safe-area insets. Keep the body
        // inside those edges too (e.g. landscape phone cutouts), not just 12px.
        let right = stage.right - 12;
        for (const element of host!.querySelectorAll('.lm-connection, .gagos-chat')) {
          const rect = element.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            left = Math.max(left, rect.left); right = Math.min(right, rect.right);
          }
        }
        width = right - left;
        const bottom = chat && chat.width > 0 && chat.height > 0 ? chat.top - 12 : stage.bottom - 12;
        height = bottom - top;
        // No usable region: retain the last projection; controls always win.
        if (width <= 0 || height <= 0 || ![left, top, width, height].every(Number.isFinite)) return;
      }
      // Retained work needs the private two-axis fit in ordinary desktop mode
      // too, so moving/side/rear roots cannot escape into its readable plane.
      // Phone/rest/short-landscape policies remain unchanged.
      if (phoneFocusRef) phoneFocusRef.current = phoneFocus || activeFocus || desktopWork;
      frame = { width, height, x: stage.left - left,
        y: stage.top - top, stageWidth: stage.width, stageHeight: stage.height };
      apply(); invalidate();
    };
    restoreFrame.current = apply;
    measure();
    const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    resize?.observe(pane); resize?.observe(canvas);
    host!.querySelectorAll('.lm-header, .gagos-experience-mode, .lm-connection, .gagos-chat')
      .forEach(element => resize?.observe(element));
    const mutation = typeof MutationObserver === 'function' ? new MutationObserver(measure) : null;
    mutation?.observe(host!, { attributes: true });
    const viewport = window.visualViewport;
    window.addEventListener('resize', measure);
    window.addEventListener('transitionend', measure, true);
    viewport?.addEventListener('resize', measure);
    viewport?.addEventListener('scroll', measure);
    return () => {
      restoreFrame.current = null;
      if (phoneFocusRef) phoneFocusRef.current = false;
      resize?.disconnect(); mutation?.disconnect();
      window.removeEventListener('resize', measure);
      window.removeEventListener('transitionend', measure, true);
      viewport?.removeEventListener('resize', measure);
      viewport?.removeEventListener('scroll', measure);
      if (previousView?.enabled) camera.setViewOffset(previousView.fullWidth, previousView.fullHeight,
        previousView.offsetX, previousView.offsetY, previousView.width, previousView.height);
      else camera.clearViewOffset();
      camera.aspect = previousAspect; camera.updateProjectionMatrix();
    };
  }, [camera, gl, invalidate, size, phoneFocusRef]);

  useFrame(() => restoreFrame.current?.(), -3);
  return null;
}
