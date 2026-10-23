'use client';
import { useLayoutEffect, useRef, type MutableRefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { PerspectiveCamera } from 'three';
import { useReducedMotion } from '@/lib/reducedMotion';
import { clearPresenceDestination, setPresenceDestination, type PresenceFrame } from '@/lib/presenceProjection';

/** One camera, two rectangles: the body keeps its authored presence pane;
 * the renderer covers the stage so its own nerves can reach the DOM controls.
 * Layout observers update a private camera adapter, not semantic body state. */
export default function PresenceViewport({ phoneFocusRef, workPaneRef, motionHeld = false }: {
  phoneFocusRef?: MutableRefObject<boolean>;
  workPaneRef?: MutableRefObject<boolean>;
  motionHeld?: boolean;
}) {
  const camera = useThree(state => state.camera);
  const gl = useThree(state => state.gl);
  const invalidate = useThree(state => state.invalidate);
  const reducedMotion = useReducedMotion();
  const suppressMotionRef = useRef(reducedMotion || motionHeld);
  suppressMotionRef.current = reducedMotion || motionHeld;
  const restoreFrame = useRef<null | (() => void)>(null);

  useLayoutEffect(() => {
    const canvas = gl.domElement;
    const host = canvas?.closest('.lm-app');
    const pane = host?.querySelector('.lm-scene');
    if (!(camera instanceof PerspectiveCamera) || !pane || !canvas) return;
    const previousView = camera.view ? { ...camera.view } : null;
    const previousAspect = camera.aspect;
    let frame: PresenceFrame | null = null;
    let destination: PresenceFrame | null = null;
    let travel: { from: PresenceFrame; started: number } | null = null;
    let lastWorking: string | null = null;
    let resize: ResizeObserver | null = null;
    const observedControls = new Set<Element>();
    const observeControls = () => {
      if (!resize) return;
      const current = new Set(host!.querySelectorAll('.lm-header, .gagos-experience-mode, .lm-navigation, .lm-connection, .gagos-chat, .gagos-status'));
      for (const element of observedControls) {
        if (!current.has(element)) { resize.unobserve(element); observedControls.delete(element); }
      }
      for (const element of current) {
        if (!observedControls.has(element)) { resize.observe(element); observedControls.add(element); }
      }
    };
    const apply = () => {
      if (travel && destination) {
        const progress = suppressMotionRef.current ? 1 : Math.min(1, Math.max(0, (performance.now() - travel.started) / 260));
        const blend = 1 - (1 - progress) ** 3;
        if (progress === 1) { frame = destination; travel = null; }
        else {
          // Private projection only: no React/layout/domain updates per frame.
          frame = { ...destination,
            width: travel.from.width + (destination.width - travel.from.width) * blend,
            height: travel.from.height + (destination.height - travel.from.height) * blend,
            x: travel.from.x + (destination.x - travel.from.x) * blend,
            y: travel.from.y + (destination.y - travel.from.y) * blend };
          invalidate();
        }
      }
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
    const measure = (immediate = false) => {
      // Mode changes can mount a new navigation row without replacing the
      // canvas. Observe the current controls, not detached previous instances.
      observeControls();
      const body = pane.getBoundingClientRect();
      const stage = canvas.getBoundingClientRect();
      if (![body.left, body.top, body.width, body.height, stage.left, stage.top, stage.width, stage.height].every(Number.isFinite)
        || body.width <= 0 || body.height <= 0 || stage.width <= 0 || stage.height <= 0) return;
      // The viewport-owned short rest layout can have a narrower canvas (a
      // native fixture scrollbar, for example). Follow its CSS presence owner,
      // not a second guessed breakpoint that installs phone Focus framing.
      // This private paint flag is read only on observer-driven measurement.
      const shortRest = host!.getAttribute('data-working') === 'false'
        && window.getComputedStyle(host!).getPropertyValue('--lm-short-rest-presence').trim() === '1';
      const narrowRest = host!.getAttribute('data-working') === 'false'
        && host!.getAttribute('data-being-focus') !== 'true'
        && window.getComputedStyle(host!).getPropertyValue('--lm-narrow-rest-presence').trim() === '1';
      const phoneFocus = host!.getAttribute('data-being-focus') === 'true' && stage.width < 768 && !shortRest;
      const activeFocus = host!.getAttribute('data-being-focus') === 'true'
        && host!.getAttribute('data-working') === 'true';
      const desktopWork = host!.getAttribute('data-working') === 'true'
        && stage.width >= 768;
      const desktopRest = host!.getAttribute('data-working') === 'false'
        && stage.width >= 768 && !shortRest;
      let left = body.left, top = body.top, width = body.width, height = body.height;
      if (narrowRest) {
        // The authored rest marker can end behind a variable-height history
        // dock. Fit its actual free portion, not a fixed phone zoom or a
        // second stage. CSS owns this policy even across scrollbar widths.
        left += 12; top += 12;
        let right = body.right - 12, bottom = body.bottom - 12;
        for (const element of host!.querySelectorAll('.lm-header, .gagos-experience-mode, .lm-navigation')) {
          const rect = element.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0 && rect.left < right && rect.right > left
            && rect.bottom > top && rect.top < bottom) top = Math.max(top, rect.bottom + 12);
        }
        const chat = host!.querySelector('.gagos-chat')?.getBoundingClientRect();
        if (chat && chat.width > 0 && chat.height > 0) {
          left = Math.max(left, chat.left); right = Math.min(right, chat.right);
          // Leave four extra pixels inside the12px control clearance for the
          // fused cord's measured breathing/orbit envelope after a resize.
          bottom = Math.min(bottom, chat.top - 16);
        }
        const notice = host!.querySelector('.lm-connection')?.getBoundingClientRect();
        if (notice && notice.width > 0 && notice.height > 0 && notice.left < right && notice.right > left
          && notice.bottom > top && notice.top < bottom) {
          if (notice.top <= top) top = Math.max(top, notice.bottom + 12);
          else bottom = Math.min(bottom, notice.top - 12);
        }
        width = right - left; height = bottom - top;
        // Keep human controls sovereign when no drawable body region remains.
        if (width <= 0 || height <= 0 || ![left, top, width, height].every(Number.isFinite)) return;
      }
      if (desktopWork || desktopRest) {
        // Ordinary retained work needs the same control-free body fit as Focus.
        // Its32% marker still includes the header/mode band; use measured rows
        // rather than shifting controls or framing the crown behind them.
        // Focus's full-width marker reaches the stage edge. Keep its fused
        // roots inside the same12px clearance as retained work, rather than
        // letting a rear resting pose consume that final control-edge gap.
        const desktopFocusRest = desktopRest && host!.getAttribute('data-being-focus') === 'true';
        let bottom = top + height - (desktopFocusRest ? 12 : 0);
        for (const element of host!.querySelectorAll('.lm-header, .gagos-experience-mode')) {
          const rect = element.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0 && rect.left < left + width && rect.right > left
            && rect.bottom > top && rect.top < bottom) top = Math.max(top, rect.bottom + 12);
        }
        if (desktopFocusRest) {
          // Focus expands the presence marker, not the space behind controls.
          // The current notice, wrapped status and draft dock still own their
          // painted bands. Reserve their measured clearance for the anatomy
          // and all retained work, without changing their layout or identity.
          const notice = host!.querySelector('.lm-connection')?.getBoundingClientRect();
          if (notice && notice.width > 0 && notice.height > 0 && notice.left < left + width && notice.right > left
            && notice.bottom > top && notice.top < bottom) top = Math.max(top, notice.bottom + 12);
          for (const element of host!.querySelectorAll('.gagos-chat, .gagos-status')) {
            const rect = element.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && rect.left < left + width && rect.right > left
              && rect.bottom > top && rect.top < bottom) bottom = Math.min(bottom, rect.top - 12);
          }
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
      // The complete short-landscape dock now uses this same work-side fit.
      // Rest, including desktop Focus, uses the same two-axis fit inside its
      // authored anatomy pane; retaining work must not shrink the being.
      if (phoneFocusRef) phoneFocusRef.current = phoneFocus || activeFocus || desktopWork || desktopRest || shortRest || narrowRest;
      // Both retained-work and narrow-rest layouts measure an anatomy-only
      // region. Returning to the intake does not restore a whole-stage card
      // composition: retained results must not shrink/lift the being again.
      // Standalone canvas choreography stays unchanged. A product rest pane
      // already owns anatomy space, independent of how many results remain.
      if (workPaneRef) workPaneRef.current = host!.getAttribute('data-working') === 'true' || narrowRest || desktopRest;
      const next = { width, height, x: stage.left - left,
        y: stage.top - top, stageWidth: stage.width, stageHeight: stage.height };
      const working = host!.getAttribute('data-working');
      const changed = !destination || Object.keys(next).some(key => next[key as keyof PresenceFrame] !== destination![key as keyof PresenceFrame]);
      const sameStage = frame?.stageWidth === next.stageWidth && frame.stageHeight === next.stageHeight;
      if (changed || immediate || suppressMotionRef.current) {
        // Refit immediately for viewport/keyboard/control safety. Only a work/
        // rest change on the same stage earns travel from the LAST painted fit.
        travel = !immediate && !suppressMotionRef.current && frame && sameStage && lastWorking !== working
          ? { from: frame, started: performance.now() } : null;
        destination = next;
        setPresenceDestination(camera, next);
        if (!travel) frame = next;
      }
      lastWorking = working;
      apply(); invalidate();
    };
    restoreFrame.current = apply;
    measure();
    resize = typeof ResizeObserver === 'function' ? new ResizeObserver(() => measure()) : null;
    resize?.observe(pane); resize?.observe(canvas);
    observeControls();
    const mutation = typeof MutationObserver === 'function' ? new MutationObserver(() => measure()) : null;
    mutation?.observe(host!, { attributes: true });
    const viewport = window.visualViewport;
    const refit = () => measure(true);
    const remeasure = () => measure();
    window.addEventListener('resize', refit);
    window.addEventListener('transitionend', remeasure, true);
    viewport?.addEventListener('resize', refit);
    viewport?.addEventListener('scroll', refit);
    return () => {
      restoreFrame.current = null;
      clearPresenceDestination(camera);
      if (phoneFocusRef) phoneFocusRef.current = false;
      if (workPaneRef) workPaneRef.current = false;
      resize?.disconnect(); mutation?.disconnect();
      window.removeEventListener('resize', refit);
      window.removeEventListener('transitionend', remeasure, true);
      viewport?.removeEventListener('resize', refit);
      viewport?.removeEventListener('scroll', refit);
      if (previousView?.enabled) camera.setViewOffset(previousView.fullWidth, previousView.fullHeight,
        previousView.offsetX, previousView.offsetY, previousView.width, previousView.height);
      else camera.clearViewOffset();
      camera.aspect = previousAspect; camera.updateProjectionMatrix();
    };
    // Renderer-size changes are observer measurements, not owner replacement.
    // Keeping this lifetime stable retains the last valid fit through an
    // unusable keyboard/dock resize; true unmount still restores the old view.
  }, [camera, gl, invalidate, phoneFocusRef, workPaneRef]);

  // An OS/app preference change settles an in-flight fit before the next paint,
  // without replacing the camera/observer lifetime or waiting for a new frame.
  useLayoutEffect(() => { if (reducedMotion || motionHeld) restoreFrame.current?.(); }, [reducedMotion, motionHeld]);

  useFrame(() => restoreFrame.current?.(), -3);
  return null;
}
