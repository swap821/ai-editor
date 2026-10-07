'use client';

import { useCallback, useEffect, useRef } from 'react';
import { addAfterEffect, addEffect, useFrame, useThree } from '@react-three/fiber';
import { useReducedMotion } from '../../lib/reducedMotion';
import { subscribeCognition } from '../../lib/cognitionBus';
import { subscribeLifecycle } from '../../lib/lifecycleStateMachine';
import { subscribeTurnMetabolism } from '../../lib/turnMetabolism';
import { subscribeTabStore } from '../../lib/tabStore';
import type { PhysicalBodyProjection } from '../../lib/bodyPosture';

// Existing posture/camera/nerve damping has a slowest rate of 2/s. A finite
// four-second window leaves <0.04% of that transition, then releases the RAF.
// This is presentation settling, never a heartbeat or a new source of work facts.
const SETTLE_MS = 4000;

export default function RenderFrameLoop({ sleeping, physical }: {
  sleeping: boolean;
  physical?: PhysicalBodyProjection;
}) {
  const reducedMotion = useReducedMotion();
  const get = useThree((state) => state.get);
  const clock = useThree((state) => state.clock);
  const setFrameloop = useThree((state) => state.setFrameloop);
  const size = useThree((state) => state.size);
  const beforeSleep = useRef<number | null>(null);
  const settleUntil = useRef(0);
  const demandIdle = useRef(true);

  useEffect(() => {
    // R3F reads Clock.getDelta BEFORE any useFrame callback. Normalize only
    // the first frame after actual root idle, regardless of who invalidated it
    // (controls, props, Suspense, or our listeners). No delta cap hides jank
    // inside an active settling window; no other root's clock is touched.
    const before = addEffect(() => {
      const state = get();
      if (state.frameloop !== 'demand' || !state.internal.active
        || state.internal.frames === 0 || !demandIdle.current) return;
      const elapsed = clock.elapsedTime;
      clock.getDelta();
      clock.elapsedTime = elapsed;
      demandIdle.current = false;
    });
    const after = addAfterEffect(() => {
      const state = get();
      demandIdle.current = state.frameloop !== 'demand'
        || !state.internal.active || state.internal.frames === 0;
    });
    return () => { before(); after(); };
  }, [clock, get]);

  const wake = useCallback(() => {
    const state = get();
    if (sleeping || !reducedMotion || state.frameloop !== 'demand') return;
    settleUntil.current = performance.now() + SETTLE_MS;
    state.invalidate();
  }, [get, reducedMotion, sleeping]);

  useEffect(() => {
    const target = sleeping ? 'never' : reducedMotion ? 'demand' : 'always';
    if (get().frameloop !== target) {
      if (sleeping) beforeSleep.current = clock.elapsedTime;
      const elapsed = sleeping ? clock.elapsedTime : beforeSleep.current ?? clock.elapsedTime;
      setFrameloop(target); // Installed R3F resets elapsedTime on every switch.
      clock.elapsedTime = elapsed;
      demandIdle.current = true;
      if (!sleeping) beforeSleep.current = null;
    }
    if (sleeping) {
      // setFrameloop('never') alone leaves a previously invalidated frame in
      // R3F's queue. Its installed loop will still paint it unless drained.
      get().internal.frames = 0;
      settleUntil.current = 0;
    }
    wake(); // Paused boot / visibility restoration still gets an actual paint.
  }, [clock, get, reducedMotion, setFrameloop, sleeping, wake]);

  useEffect(() => {
    wake();
  }, [wake, size.width, size.height, size.left, size.top,
    physical?.phase, physical?.taskState, physical?.coherence, physical?.motion,
    physical?.cortex.posture, physical?.verification.state, physical?.membrane.state]);

  useEffect(() => {
    if (sleeping || !reducedMotion) return;
    const unsubscribes = [subscribeCognition(wake), subscribeLifecycle(wake),
      subscribeTurnMetabolism(wake), subscribeTabStore(wake)];
    // DOM intake can translate without changing either Canvas or dock size.
    // VisualViewport events are dispatched on their own target, not window.
    const events = ['pointermove', 'pointerdown', 'input', 'keydown', 'focusin', 'scroll', 'resize', 'transitionend', 'gagos:ready'] as const;
    for (const event of events) window.addEventListener(event, wake, { passive: true, capture: true });
    const viewport = window.visualViewport;
    viewport?.addEventListener('resize', wake, { passive: true });
    viewport?.addEventListener('scroll', wake, { passive: true });
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(wake);
    const dock = document.querySelector('.gagos-bar');
    if (dock) observer?.observe(dock);
    const canvas = get().gl.domElement;
    canvas.addEventListener('webglcontextrestored', wake);
    return () => {
      for (const unsubscribe of unsubscribes) unsubscribe();
      for (const event of events) window.removeEventListener(event, wake, true);
      viewport?.removeEventListener('resize', wake);
      viewport?.removeEventListener('scroll', wake);
      observer?.disconnect();
      canvas.removeEventListener('webglcontextrestored', wake);
    };
  }, [get, reducedMotion, sleeping, wake]);

  useFrame((state) => {
    if (state.frameloop === 'demand' && !sleeping && performance.now() < settleUntil.current) {
      state.invalidate(); // Default priority: never takes rendering from PostFX.
    }
  });
  return null;
}
