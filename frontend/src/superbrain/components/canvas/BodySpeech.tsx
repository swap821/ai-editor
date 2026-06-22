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
import { deriveBodySpeech } from '@/lib/bodySpeech';

interface TroikaText {
  text: string;
  fillOpacity: number;
  outlineOpacity: number;
  sync: () => void;
}

const REDUCED =
  typeof window !== 'undefined' &&
  !!window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function BodySpeech({ color = '#7bf5fb' }: { color?: string }) {
  const groupRef = useRef<THREE.Group>(null);
  const textRef = useRef<TroikaText | null>(null);
  const col = useMemo(() => new THREE.Color(color), [color]);
  const lastText = useRef<string>('');

  useFrame(() => {
    const g = groupRef.current;
    const t = textRef.current;
    if (!g || !t) return;
    const v = getReplyVoice();
    const o = deriveBodySpeech({
      text: v.text,
      phase: v.phase,
      sinceMs: performance.now() - v.since,
      reducedMotion: REDUCED,
    });
    g.visible = o.active;
    if (!o.active) return;
    if (o.visibleText !== lastText.current) {
      t.text = o.visibleText;
      t.sync();
      lastText.current = o.visibleText;
    }
    const op = (1 - o.fade) * (0.5 + 0.5 * o.glow);
    t.fillOpacity = op;
    t.outlineOpacity = op * 0.6;
  });

  return (
    <Billboard>
      {/* Placement: a readable default above the cortex; the operator fine-tunes on
          his RTX (this project defers final visual placement to his eye). */}
      <group ref={groupRef} position={[0, 0.92, 0.35]} visible={false}>
        <Text
          ref={textRef as never}
          color={col}
          fontSize={0.085}
          maxWidth={2.4}
          lineHeight={1.25}
          anchorX="center"
          anchorY="top"
          textAlign="center"
          outlineWidth={0.006}
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
