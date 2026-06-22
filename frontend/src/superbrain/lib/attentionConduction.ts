import type { AttentionTransfer, MaterializedTabRecord } from './tabStore';

export type Vec3Tuple = [number, number, number];

export interface AttentionConductionPath {
  fromId: string;
  toId: string;
  direction: AttentionTransfer['direction'];
  startedAt: number;
  durationMs: number;
  start: Vec3Tuple;
  midA: Vec3Tuple;
  midB: Vec3Tuple;
  end: Vec3Tuple;
}

const PULSE_DURATION_MS = 920;

function tuple(x: number, y: number, z: number): Vec3Tuple {
  return [Number(x.toFixed(4)), Number(y.toFixed(4)), Number(z.toFixed(4))];
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function isConductable(tab: MaterializedTabRecord): boolean {
  return tab.kind !== 'input' && tab.lifecycle !== 'retracting';
}

export function deriveAttentionConductionPath(
  tabs: readonly MaterializedTabRecord[],
  attention: AttentionTransfer | null,
): AttentionConductionPath | null {
  if (!attention?.fromId || attention.fromId === attention.toId) return null;

  const from = tabs.find((tab) => tab.id === attention.fromId && tab.kind !== 'input');
  const to = tabs.find((tab) => tab.id === attention.toId && isConductable(tab));
  if (!from || !to) return null;

  const [fromX, fromY, fromZ] = from.originLocal;
  const [toX, toY, toZ] = to.originLocal;
  const directionOffset = attention.direction === 'backward' ? -0.025 : attention.direction === 'forward' ? 0.025 : 0.01;
  const spineZ = Math.max(fromZ, toZ) + 0.095;

  return {
    fromId: from.id,
    toId: to.id,
    direction: attention.direction,
    startedAt: attention.startedAt,
    durationMs: PULSE_DURATION_MS,
    start: tuple(fromX * 0.35, fromY, fromZ + 0.045),
    midA: tuple(directionOffset, lerp(fromY, toY, 0.36), spineZ),
    midB: tuple(directionOffset * 0.65, lerp(fromY, toY, 0.72), spineZ),
    end: tuple(toX * 0.35, toY, toZ + 0.045),
  };
}
