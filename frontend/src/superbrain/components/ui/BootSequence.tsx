'use client';

/**
 * BootSequence — GAGOS kernel boot overlay.
 *
 * Fullscreen overlay above the HUD while the Canvas underneath compiles
 * shaders and loads the GLB. The progress bar blends REAL asset progress
 * (drei's useProgress zustand store works outside the Canvas — it reads the
 * shared loading state) with a scripted minimum, so boot lands at ~2.6s
 * nominal and never exceeds ~3.4s even when assets stall or are uncached.
 *
 * Any click or keypress skips straight to the finale. After the finale
 * sweep and a 500ms fade the component renders null — it never leaves an
 * invisible overlay intercepting pointer events, and never re-mounts.
 */

import { useEffect, useRef, useState } from 'react';
import { useProgress } from '@react-three/drei';
import { publishCognition } from '@/lib/cognitionBus';
import { transitionToArriving, ArrivalMode } from '@/lib/lifecycleStateMachine';
import { AIOS_BASE } from '@/lib/aiosAdapter';
import styles from './BootSequence.module.css';

interface BootLine {
  text: string;
  status?: string;
  head?: boolean;
}

const BOOT_LINES: BootLine[] = [
  { text: 'GAGOS KERNEL v2.6 — NOUMENON PROTOCOL', head: true },
  { text: 'verifying fable-class cognition core', status: 'OK' },
  { text: 'mounting cortical lattice [2,605 nodes]', status: 'OK' },
  { text: 'binding agent mesh', status: '9 / 15 ENGAGED' },
  { text: 'indexing knowledge horizon', status: '18.23 GB' },
  { text: 'establishing historical mythos link', status: 'CONFIRMED' },
  { text: 'calibrating supermind', status: 'NOMINAL' },
];

import { useMirrorStore } from '@/lib/mirrorStore';

interface BootTimings {
  /** ms per boot-log line (0 = all lines instantly). */
  line: number;
  /** Nominal scripted ramp — bar completes here when assets are ready. */
  ramp: number;
  /** Hard ceiling — bar is forced full here even if assets report nothing. */
  bar: number;
  /** "GAGOS ONLINE" sweep duration. */
  finale: number;
  /** Fade-out duration before full unmount. */
  fade: number;
}

/** Nominal: 1700 + 420 + 500 ≈ 2.6s. Worst case: 2480 + 420 + 500 ≈ 3.4s. */
const NORMAL_TIMINGS: BootTimings = { line: 140, ramp: 1700, bar: 2480, finale: 420, fade: 500 };
/** prefers-reduced-motion: no typing, ~1.2s total. */
const REDUCED_TIMINGS: BootTimings = { line: 0, ramp: 350, bar: 550, finale: 320, fade: 300 };

type Phase = 'log' | 'finale' | 'fade' | 'done';

const HexMark = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3 4.5 7.2v9.6L12 21l7.5-4.2V7.2L12 3Zm0 4.2 3.8 2.1v5.4L12 16.8l-3.8-2.1V9.3L12 7.2Z" />
  </svg>
);

export default function BootSequence({ onComplete }: { onComplete: () => void }) {
  const [phase, setPhase] = useState<Phase>('log');
  const [lineCount, setLineCount] = useState(0);
  const [reducedMotion] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  const fillRef = useRef<HTMLSpanElement>(null);
  const skipRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  // TRUE BOOT: real facts are published via the mirror snapshot at boot.
  // We subscribe to the store, and if bootFacts arrive within the budget, we render them.
  const [lines, setLines] = useState<BootLine[]>(BOOT_LINES);
  
  useEffect(() => {
    let timeoutId = 0;
    const unsub = useMirrorStore.subscribe(
      (state) => state.bootFacts,
      (facts) => {
        if (!facts) return;
        setLines((prev) =>
          prev.map((line) => {
            let status;
            if (line.text.includes('fable-class cognition core')) {
              status = `v${facts.version || 'unknown'} OK`;
            } else if (line.text.includes('cortical lattice')) {
              status = `[${facts.nodes_count ?? 'UNKNOWN'} nodes]`;
            } else if (line.text.includes('binding agent mesh')) {
              const avg = typeof facts.average_tool_calls === 'number' ? facts.average_tool_calls.toFixed(1) : '?';
              status = `AVG ${avg} CALLS/TURN`;
            } else if (line.text.includes('indexing knowledge horizon')) {
              status = `${facts.trails_total ?? '?'} TRAILS · ${facts.trails_verified ?? '?'} VERIFIED`;
            } else if (line.text.includes('historical mythos link')) {
              status = 'LIVE';
            } else if (line.text.includes('calibrating supermind')) {
              const rate = typeof facts.verified_success_rate === 'number' ? Math.round(facts.verified_success_rate * 100) : '?';
              status = `${rate}% VERIFIED RATE`;
            }
            return status ? { ...line, status } : line;
          })
        );
      },
      { fireImmediately: true }
    );

    // After budget time, we stop listening so we don't accidentally update lines 
    // mid-animation. Offline boot retains lore.
    timeoutId = window.setTimeout(() => {
      unsub();
    }, BOOT_FACTS_BUDGET_MS);

    return () => {
      window.clearTimeout(timeoutId);
      unsub();
    };
  }, []);

  const timings = reducedMotion ? REDUCED_TIMINGS : NORMAL_TIMINGS;

  // Skippable: any click or keypress jumps straight to the finale.
  useEffect(() => {
    if (phase !== 'log') return;
    const skip = () => {
      skipRef.current = true;
    };
    window.addEventListener('pointerdown', skip, true);
    window.addEventListener('keydown', skip, true);
    return () => {
      window.removeEventListener('pointerdown', skip, true);
      window.removeEventListener('keydown', skip, true);
    };
  }, [phase]);

  // Boot driver: reveals log lines and advances the progress bar each frame.
  useEffect(() => {
    if (phase !== 'log') return;
    const start = performance.now();
    let raf = 0;

    const frame = (now: number) => {
      const elapsed = now - start;

      const targetLines = skipRef.current
        ? BOOT_LINES.length
        : timings.line === 0
          ? BOOT_LINES.length
          : Math.min(BOOT_LINES.length, Math.floor(elapsed / timings.line) + 1);
      setLineCount((prev) => (targetLines > prev ? targetLines : prev));

      // Blend real asset progress with the scripted minimum. Real progress
      // can accelerate the ramp but never stall it past the hard ceiling.
      const real = useProgress.getState().progress / 100;
      const ramp = Math.min(1, elapsed / timings.ramp);
      const forced = Math.min(1, elapsed / timings.bar);
      const value = skipRef.current
        ? 1
        : Math.max(forced, Math.min(1, ramp * (0.55 + 0.45 * Math.max(real, forced))));

      if (fillRef.current) {
        fillRef.current.style.transform = `scaleX(${value.toFixed(4)})`;
      }

      if (skipRef.current || (value >= 1 && targetLines >= BOOT_LINES.length)) {
        setLineCount(BOOT_LINES.length);
        setPhase('finale');
        return;
      }
      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [phase, timings]);

  // Finale sweep -> fade-out -> full unmount.
  useEffect(() => {
    if (phase === 'finale') {
      const id = window.setTimeout(() => setPhase('fade'), timings.finale);
      return () => window.clearTimeout(id);
    }
    if (phase === 'fade') {
      publishCognition({
        type: 'synthesis',
        label: 'GAGOS ONLINE',
        detail: 'GAGOS kernel boot complete — cognition core engaged.',
        intensity: 0.9,
        source: 'boot',
      });
      // The kernel is online — begin the being's opening. First-ever load on this
      // device coalesces (A); a return awakens (C). Reduced-motion is honored by
      // the scene (it renders the settled REST state immediately).
      let firstEver = true;
      try {
        firstEver = window.localStorage.getItem('gag-has-arrived-v1') === null;
        window.localStorage.setItem('gag-has-arrived-v1', '1');
      } catch {
        // Private mode: treat as first-ever (coalescence) — the richer opening.
      }
      transitionToArriving(firstEver ? ArrivalMode.COALESCENCE : ArrivalMode.AWAKENING);
      const id = window.setTimeout(() => {
        setPhase('done');
        onCompleteRef.current();
      }, timings.fade);
      return () => window.clearTimeout(id);
    }
  }, [phase, timings]);

  if (phase === 'done') return null;

  return (
    <div
      className={phase === 'fade' ? `${styles.overlay} ${styles.isFading}` : styles.overlay}
      role="status"
      aria-label="GAGOS boot sequence"
    >
      <span className={styles.mark} aria-hidden="true">
        <HexMark />
      </span>

      <div className={styles.stage}>
        {phase === 'log' ? (
          <>
            <div className={styles.log}>
              {lines.map((line, index) => (
                <p
                  key={line.text}
                  className={index < lineCount ? `${styles.line} ${styles.lineVisible}` : styles.line}
                >
                  {line.head ? (
                    <span className={styles.head}>{line.text}</span>
                  ) : (
                    <>
                      {line.text} <span className={styles.dots}>...</span>{' '}
                      <span className={styles.status}>{line.status}</span>
                    </>
                  )}
                </p>
              ))}
            </div>
            <div className={styles.track}>
              <span ref={fillRef} className={styles.fill} />
            </div>
          </>
        ) : (
          <p className={styles.finale}>GAGOS ONLINE</p>
        )}
      </div>
    </div>
  );
}
