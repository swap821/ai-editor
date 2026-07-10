import { Text, Line } from '@react-three/drei';
import { useMemo } from 'react';
import * as THREE from 'three';
import { useMetric, useMetricHistory, type MetricKey } from '@/lib/metricsStore';
import type { SurfaceTheme } from './theme';

/**
 * Small always-on metrics readout (research/memory/tools/signals bars +
 * a tools sparkline) shown on a focused work tab. Extracted from
 * MaterializedTab.tsx (structure audit, 2026-07-10). Re-renders on the
 * metrics store tick (~1.8s) via useSyncExternalStore inside useMetric --
 * no per-frame cost. Colors are theme tokens only (sacred palette preserved).
 */
const DASH_CHANNELS: ReadonlyArray<{ key: MetricKey; label: string }> = [
  { key: 'research', label: 'R' },
  { key: 'memory', label: 'M' },
  { key: 'tools', label: 'T' },
  { key: 'signals', label: 'S' },
];

export function WorkTabLiveDashboard({
  width,
  height,
  z,
  theme,
}: {
  width: number;
  height: number;
  z: number;
  theme: SurfaceTheme;
}) {
  const research = useMetric('research');
  const memory = useMetric('memory');
  const tools = useMetric('tools');
  const signals = useMetric('signals');
  const toolsHistory = useMetricHistory('tools');
  const values: Record<MetricKey, number> = { research, memory, tools, signals };

  const x0 = width * 0.08; // first bar x (right half; code lives on the left)
  const dx = width * 0.09; // bar spacing
  const barW = width * 0.05;
  const baseY = -height * 0.08; // bar baseline
  const maxBarH = height * 0.2; // value 99 -> full height

  const sparkPoints = useMemo<[number, number, number][] | null>(() => {
    if (toolsHistory.length < 2) return null;
    const n = toolsHistory.length;
    const sx0 = x0 - dx * 0.45;
    const sw = dx * (DASH_CHANNELS.length - 1) + barW;
    const sy = baseY + maxBarH + height * 0.05;
    return toolsHistory.map(
      (v, i) => [sx0 + (sw * i) / (n - 1), sy + (v / 99) * (height * 0.06), z] as [number, number, number],
    );
  }, [toolsHistory, x0, dx, barW, baseY, maxBarH, height, z]);

  return (
    <group renderOrder={11}>
      <Text
        position={[x0 - dx * 0.45, baseY + maxBarH + height * 0.13, z]}
        color={theme.live}
        fontSize={0.02}
        anchorX="left"
        anchorY="middle"
        outlineWidth={0.0014}
        outlineColor={theme.outline}
        renderOrder={11}
      >
        LIVE · BODY
      </Text>
      {DASH_CHANNELS.map((ch, i) => {
        const v = values[ch.key];
        const bh = Math.max(0.004, (v / 99) * maxBarH);
        const x = x0 + i * dx;
        return (
          <group key={ch.key}>
            <mesh position={[x, baseY + maxBarH * 0.5, z - 0.002]} renderOrder={10}>
              <planeGeometry args={[barW, maxBarH]} />
              <meshBasicMaterial color={theme.muted} transparent opacity={0.16} depthWrite={false} />
            </mesh>
            <mesh position={[x, baseY + bh * 0.5, z]} renderOrder={11}>
              <planeGeometry args={[barW, bh]} />
              <meshBasicMaterial
                color={theme.accent}
                transparent
                opacity={0.92}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
            <Text position={[x, baseY - height * 0.04, z]} color={theme.header} fontSize={0.018} anchorX="center" anchorY="middle" renderOrder={11}>
              {ch.label}
            </Text>
          </group>
        );
      })}
      {sparkPoints && (
        <Line points={sparkPoints} color={theme.live} lineWidth={1.4} transparent opacity={0.8} renderOrder={11} />
      )}
    </group>
  );
}
