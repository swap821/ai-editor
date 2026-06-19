import { describe, expect, it } from 'vitest';
import { deriveLivingOrchestration, type LivingLifecycleState } from './livingOrchestrator';
import type { MaterializedTabKind, MaterializedTabRecord, TabLifecycle } from './tabStore';

function tab(
  id: string,
  kind: MaterializedTabKind,
  lifecycle: TabLifecycle = 'live',
  seatIndex: number | null = kind === 'input' ? null : 2,
): MaterializedTabRecord {
  return {
    id,
    kind,
    lifecycle,
    originLocal: [0, 0, 0],
    targetLocal: [1, 0, 0],
    seatIndex,
    content: kind === 'content' ? { code: 'print(1)', language: 'python', filepath: `${id}.py` } : null,
    input: kind === 'input' ? { text: 'build the living mechanism' } : null,
    approval:
      kind === 'approval'
        ? {
            token: 'tok-1',
            summary: 'Approval required',
            explanation: 'Needs operator consent',
            diff: '+print(1)\n',
            command: '',
            kindLabel: 'create',
            filepath: `${id}.py`,
            content: 'print(1)\n',
          }
        : null,
    bornAt: 0,
    phaseStartedAt: 0,
  };
}

function phase(lifecycleState: LivingLifecycleState) {
  return deriveLivingOrchestration({ lifecycleState, tabs: [], focusId: null }).phase;
}

describe('livingOrchestrator', () => {
  it('maps the body lifecycle when there are no materialized surfaces', () => {
    expect(phase('booting')).toBe('booting');
    expect(phase('arriving')).toBe('arrival');
    expect(phase('rest')).toBe('rest');
    expect(phase('attentive')).toBe('attentive');
  });

  it('keeps the brainstem intake visible without counting it as workspace', () => {
    const orchestration = deriveLivingOrchestration({
      lifecycleState: 'attentive',
      tabs: [tab('input-1', 'input')],
      focusId: null,
    });

    expect(orchestration.phase).toBe('attentive');
    expect(orchestration.workspaceCount).toBe(0);
    expect(orchestration.visibleCount).toBe(1);
    expect(orchestration.surfaces).toHaveLength(1);
    expect(orchestration.surfaces[0]).toMatchObject({ role: 'intake', focused: true, waitingIndex: 0 });
  });

  it('treats a reaching workspace as materialization before working/conducting', () => {
    const orchestration = deriveLivingOrchestration({
      tabs: [tab('content-1', 'content', 'reaching', 2)],
      focusId: 'content-1',
    });

    expect(orchestration.phase).toBe('materializing');
    expect(orchestration.materializing).toBe(true);
    expect(orchestration.focusId).toBe('content-1');
    expect(orchestration.activeSeatIndex).toBe(2);
  });

  it('conducts multiple live workspace surfaces with a focused center and waiting order', () => {
    const orchestration = deriveLivingOrchestration({
      tabs: [tab('input-1', 'input'), tab('content-1', 'content', 'live', 2), tab('content-2', 'content', 'live', 3)],
      focusId: 'content-2',
      attention: { fromId: 'content-1', toId: 'content-2', direction: 'forward', startedAt: 1500 },
    });

    expect(orchestration.phase).toBe('conducting');
    expect(orchestration.workspaceCount).toBe(2);
    expect(orchestration.focusId).toBe('content-2');
    expect(orchestration.conductorOrder).toEqual(['content-1', 'content-2']);
    expect(orchestration.activeConductionIndex).toBe(1);
    expect(orchestration.previousFocusId).toBe('content-1');
    expect(orchestration.nextFocusId).toBe('content-1');
    expect(orchestration.attention).toMatchObject({
      fromId: 'content-1',
      toId: 'content-2',
      direction: 'forward',
    });
    expect(orchestration.surfaces.map((surface) => [surface.tab.id, surface.role, surface.waitingIndex])).toEqual([
      ['input-1', 'intake', 0],
      ['content-1', 'waiting', 0],
      ['content-2', 'focus', 0],
    ]);
  });

  it('orders conduction by vertebra seat rather than creation order', () => {
    const orchestration = deriveLivingOrchestration({
      tabs: [
        tab('content-lower', 'content', 'live', 5),
        tab('content-upper', 'content', 'live', 2),
        tab('content-middle', 'content', 'live', 3),
      ],
      focusId: 'content-middle',
    });

    expect(orchestration.phase).toBe('conducting');
    expect(orchestration.conductorOrder).toEqual(['content-upper', 'content-middle', 'content-lower']);
    expect(orchestration.activeConductionIndex).toBe(1);
    expect(orchestration.previousFocusId).toBe('content-upper');
    expect(orchestration.nextFocusId).toBe('content-lower');
    expect(orchestration.surfaces.map((surface) => [surface.tab.id, surface.role, surface.waitingIndex])).toEqual([
      ['content-upper', 'waiting', 0],
      ['content-lower', 'waiting', 1],
      ['content-middle', 'focus', 0],
    ]);
  });

  it('drops stale attention when it does not belong to the current conductor', () => {
    const orchestration = deriveLivingOrchestration({
      tabs: [tab('content-1', 'content', 'live', 2), tab('input-1', 'input')],
      focusId: 'content-1',
      attention: { fromId: 'input-1', toId: 'content-1', direction: 'direct', startedAt: 10 },
    });

    expect(orchestration.attention).toBeNull();
  });

  it('lets approval hold override ordinary conducting', () => {
    const orchestration = deriveLivingOrchestration({
      tabs: [tab('content-1', 'content', 'live', 2), tab('approval-1', 'approval', 'live', 3)],
      focusId: 'approval-1',
    });

    expect(orchestration.phase).toBe('approval_hold');
    expect(orchestration.approvalHeld).toBe(true);
    expect(orchestration.focusKind).toBe('approval');
  });

  it('keeps retracting surfaces renderable while the body reabsorbs them', () => {
    const orchestration = deriveLivingOrchestration({
      tabs: [tab('content-1', 'content', 'retracting', 2)],
      focusId: 'content-1',
    });

    expect(orchestration.phase).toBe('reabsorbing');
    expect(orchestration.workspaceCount).toBe(0);
    expect(orchestration.surfaces[0]).toMatchObject({ role: 'reabsorbing', focused: false });
  });
});
