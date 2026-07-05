'use client';
// BodySpeech (poster phase 3): the being's reply as luminous body-speech — drei <Text>
// near the cortex, billboarded to the camera, streaming + settling per deriveBodySpeech.
// Reads the reply off replyVoiceBus; the renderer invents nothing. Luminance/text only
// (sacred palette held — colour is a posture/theme hue passed in).
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text, Billboard } from '@react-three/drei';
import * as THREE from 'three';
import { getReplyVoice } from '@/lib/replyVoiceBus';
import { deriveBodySpeech, decideBodySpeechSync } from '@/lib/bodySpeech';
import { useReducedMotion } from '@/lib/reducedMotion';

interface TroikaText {
  text: string;
  fillOpacity: number;
  outlineOpacity: number;
  sync: (callback?: () => void) => void;
  // Internal troika-three-text bookkeeping (not in its public typings) — only
  // touched defensively on the force-resync path, see the comment below.
  _isSyncing?: boolean;
  _needsSync?: boolean;
  _queuedSyncs?: unknown[] | null;
}

export default function BodySpeech({ color = '#7bf5fb' }: { color?: string }) {
  const groupRef = useRef<THREE.Group>(null);
  const textRef = useRef<TroikaText | null>(null);
  const col = useMemo(() => new THREE.Color(color), [color]);
  const lastText = useRef<string>('');
  // Watchdog bookkeeping for the troika sync-stall recovery below (real defect,
  // 2026-07-05 — see decideBodySpeechSync's doc comment in bodySpeech.ts).
  const syncPending = useRef(false);
  const syncPendingSinceMs = useRef(0);
  // REACTIVE reduced-motion (was a once-at-import module const) — the useFrame
  // closure re-reads it on the re-render when the OS setting flips.
  const reduced = useReducedMotion();

  useFrame(() => {
    const g = groupRef.current;
    const t = textRef.current;
    if (!g || !t) return;
    const v = getReplyVoice();
    const o = deriveBodySpeech({
      text: v.text,
      phase: v.phase,
      sinceMs: performance.now() - v.since,
      reducedMotion: reduced,
    });
    g.visible = o.active;
    if (!o.active) return;

    const nowMs = performance.now();
    const action = decideBodySpeechSync(
      o.visibleText,
      lastText.current,
      syncPending.current,
      syncPendingSinceMs.current,
      nowMs,
    );
    if (action !== 'skip') {
      if (action === 'force-resync') {
        // troika-three-text's sync() has no error handling anywhere in its async
        // chain (font load + SDF glyph generation) — if that chain never settles
        // (a transient WebGL hiccup during first-time glyph-atlas creation is the
        // realistic trigger), its internal `_isSyncing` flag is stuck `true`
        // forever and every later `.sync()` call just silently queues behind the
        // dead one: nothing throws, nothing logs, the glyph geometry is simply
        // never rebuilt again — the reply becomes permanently invisible even
        // though the cognition bus reports a perfectly healthy phase and full
        // text (confirmed live via a controlled repro). Rather than trust a
        // stuck in-flight sync to ever resolve, force troika's internal guards
        // back to a clean state so the next sync() call actually runs.
        t._isSyncing = false;
        t._needsSync = true;
        t._queuedSyncs = null;
      }
      t.text = o.visibleText;
      if (!syncPending.current) {
        syncPendingSinceMs.current = nowMs;
      }
      syncPending.current = true;
      try {
        t.sync(() => {
          syncPending.current = false;
        });
      } catch {
        // A synchronous throw here means this attempt never truly started;
        // let the watchdog's stall timeout retry on a later frame.
      }
      lastText.current = o.visibleText;
    }

    const op = (1 - o.fade) * (0.5 + 0.5 * o.glow);
    t.fillOpacity = op;
    t.outlineOpacity = op * 0.6;
  });

  return (
    <Billboard>
      {/* Placement: the being's words flow out to the RIGHT of its head into the dark
          void — readable (off the bright cortex) yet clearly tethered to the mind that
          speaks them. Billboarded to the camera. */}
      <group ref={groupRef} position={[1.25, 0.62, 0.35]} visible={false}>
        <Text
          ref={textRef as never}
          color={col}
          fontSize={0.082}
          maxWidth={1.7}
          lineHeight={1.3}
          anchorX="left"
          anchorY="top"
          textAlign="left"
          outlineWidth={0.008}
          outlineColor="#02040a"
          material-toneMapped={false}
          renderOrder={12}
        >
          {''}
        </Text>
      </group>
    </Billboard>
  );
}
