import { describe, expect, it } from 'vitest';
import { deriveAttentionConductionPath } from './attentionConduction';
import type { AttentionTransfer, MaterializedTabKind, MaterializedTabRecord, TabLifecycle } from './tabStore';

function tab(
  id: string,
  kind: MaterializedTabKind,
  originLocal: [number, number, number],
  lifecycle: TabLifecycle = 'live',
): MaterializedTabRecord {
  return {
    id,
    kind,
    lifecycle,
    originLocal,
    targetLocal: [1, 0, 0],
    seatIndex: kind === 'input' ? null : 2,
    content: kind === 'content' ? { code: 'print(1)', language: 'python', filepath: `${id}.py` } : null,
    input: kind === 'input' ? { text: 'build' } : null,
    approval: null,
    bornAt: 0,
    phaseStartedAt: 0,
  };
}

function transfer(partial: Partial<AttentionTransfer> = {}): AttentionTransfer {
  return {
    fromId: 'upper',
    toId: 'lower',
    direction: 'forward',
    startedAt: 1200,
    ...partial,
  };
}

describe('attentionConduction', () => {
  it('derives a visible pulse path between the previous and attended vertebra origins', () => {
    const path = deriveAttentionConductionPath(
      [
        tab('upper', 'content', [0.04, -1, -0.38]),
        tab('lower', 'content', [0.08, -1.72, -0.34]),
      ],
      transfer(),
    );

    expect(path).toMatchObject({
      fromId: 'upper',
      toId: 'lower',
      direction: 'forward',
      startedAt: 1200,
      durationMs: 920,
    });
    expect(path?.start[1]).toBe(-1);
    expect(path?.end[1]).toBe(-1.72);
    expect(path?.midA[2]).toBeGreaterThan(-0.34);
  });

  it('does not conduct from intake, missing, same, or retracting targets', () => {
    const tabs = [
      tab('upper', 'content', [0, -1, -0.38]),
      tab('lower', 'content', [0, -1.5, -0.38], 'retracting'),
      tab('input', 'input', [0, -0.2, -0.38]),
    ];

    expect(deriveAttentionConductionPath(tabs, null)).toBeNull();
    expect(deriveAttentionConductionPath(tabs, transfer({ fromId: null }))).toBeNull();
    expect(deriveAttentionConductionPath(tabs, transfer({ fromId: 'upper', toId: 'upper' }))).toBeNull();
    expect(deriveAttentionConductionPath(tabs, transfer({ fromId: 'input', toId: 'upper' }))).toBeNull();
    expect(deriveAttentionConductionPath(tabs, transfer({ fromId: 'upper', toId: 'lower' }))).toBeNull();
  });
});
