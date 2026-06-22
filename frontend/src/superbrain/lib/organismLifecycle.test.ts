import { describe, expect, it } from 'vitest';
import { type AnatomicalRootSystemSnapshot } from './anatomicalRootSystem';
import { REST_COMPLETION_REFLEX, type CompletionReflexSnapshot } from './completionReflex';
import { deriveLivingOrchestration } from './livingOrchestrator';
import { deriveOrganismLifecycle } from './organismLifecycle';
import { REST_OUTCOME_IMPRINT, type OutcomeImprintSnapshot } from './outcomeImprint';
import type { MaterializedTabKind, MaterializedTabRecord, TabLifecycle } from './tabStore';
import { REST_TURN_METABOLISM, type TurnMetabolismSnapshot } from './turnMetabolism';

function tab(
  id: string,
  kind: MaterializedTabKind,
  options: {
    lifecycle?: TabLifecycle;
    seatIndex?: number | null;
    bornAt?: number;
    filepath?: string;
  } = {},
): MaterializedTabRecord {
  const lifecycle = options.lifecycle ?? 'live';
  const seatIndex = options.seatIndex ?? (kind === 'input' ? null : 2);
  const filepath = options.filepath ?? `${id}.ts`;
  return {
    id,
    kind,
    lifecycle,
    originLocal: [0, 0, 0],
    targetLocal: [kind === 'content' ? 1 : 0.2, 0, 0],
    seatIndex,
    content: kind === 'content' ? { code: 'export const value = true;', language: 'typescript', filepath } : null,
    input: kind === 'input' ? { text: 'build the lifecycle organism' } : null,
    approval:
      kind === 'approval'
        ? {
            token: 'tok-1',
            summary: 'Approval required',
            explanation: 'Needs operator consent',
            diff: '+export const value = true;\n',
            command: '',
            kindLabel: 'create',
            filepath,
            content: 'export const value = true;\n',
          }
        : null,
    bornAt: options.bornAt ?? 0,
    phaseStartedAt: options.bornAt ?? 0,
  };
}

const workingMetabolism: TurnMetabolismSnapshot = {
  ...REST_TURN_METABOLISM,
  phase: 'working',
  intensity: 1,
  surfaceExcitation: 0.55,
  rootExcitation: 0.7,
  breathGain: 0.32,
  changedAt: 100,
};

const approvalMetabolism: TurnMetabolismSnapshot = {
  ...REST_TURN_METABOLISM,
  phase: 'approval',
  intensity: 1,
  held: true,
  changedAt: 120,
};

const errorMetabolism: TurnMetabolismSnapshot = {
  ...REST_TURN_METABOLISM,
  phase: 'error',
  intensity: 1,
  changedAt: 140,
};

const scarOutcome: OutcomeImprintSnapshot = {
  ...REST_OUTCOME_IMPRINT,
  kind: 'scar',
  intensity: 1,
  rootGlow: 0.7,
  tint: '#ff5f7a',
  changedAt: 150,
};

function completion(partial: Partial<CompletionReflexSnapshot>): CompletionReflexSnapshot {
  return {
    ...REST_COMPLETION_REFLEX,
    ...partial,
  };
}

function roots(partial: Partial<AnatomicalRootSystemSnapshot> = {}): AnatomicalRootSystemSnapshot {
  return {
    strands: [],
    caudaTraces: [],
    activeSeatIndexes: [],
    waitingSeatIndexes: [],
    heldSeatIndexes: [],
    errorSeatIndexes: [],
    reabsorbingSeatIndexes: [],
    sprayIntensity: 0,
    dominantRole: 'resting',
    ...partial,
  };
}

function lifecycle(
  tabs: MaterializedTabRecord[],
  options: {
    focusId?: string | null;
    metabolism?: TurnMetabolismSnapshot;
    outcome?: OutcomeImprintSnapshot;
    completion?: CompletionReflexSnapshot;
    rootSystem?: AnatomicalRootSystemSnapshot;
  } = {},
) {
  const orchestration = deriveLivingOrchestration({
    tabs,
    focusId: options.focusId ?? null,
  });
  return deriveOrganismLifecycle({
    orchestration,
    metabolism: options.metabolism ?? REST_TURN_METABOLISM,
    outcome: options.outcome ?? REST_OUTCOME_IMPRINT,
    completion: options.completion ?? REST_COMPLETION_REFLEX,
    rootSystem: options.rootSystem ?? roots(),
  });
}

describe('organismLifecycle', () => {
  it('keeps rest as a valid breathing organism state', () => {
    const state = lifecycle([]);
    expect(state.phase).toBe('rest');
    expect(state.posture).toBe('breathing');
    expect(state.invariant.valid).toBe(true);
    expect(state.activeSurfaceId).toBeNull();
  });

  it('treats a lone input surface as intake, not workspace', () => {
    const input = tab('input-1', 'input');
    const state = lifecycle([input]);
    expect(state.phase).toBe('intake');
    expect(state.bodyEvent).toBe('intent_rise');
    expect(state.intakeSurfaceId).toBe(input.id);
    expect(state.workspaceCount).toBe(0);
    expect(state.surfaces[0]).toMatchObject({ id: input.id, bodyRole: 'intake', stale: false });
  });

  it('promotes a reaching content surface to surface birth', () => {
    const content = tab('content-1', 'content', { lifecycle: 'reaching', seatIndex: 2 });
    const state = lifecycle([content], { focusId: content.id });
    expect(state.phase).toBe('materializing');
    expect(state.posture).toBe('forming_surface');
    expect(state.activeSurfaceId).toBe(content.id);
  });

  it('conducts multiple work surfaces through one ordered body state', () => {
    const upper = tab('content-upper', 'content', { seatIndex: 2, bornAt: 1 });
    const lower = tab('content-lower', 'content', { seatIndex: 5, bornAt: 2 });
    const state = lifecycle([lower, upper], {
      focusId: lower.id,
      metabolism: workingMetabolism,
      rootSystem: roots({ dominantRole: 'conducting', activeSeatIndexes: [5], waitingSeatIndexes: [2] }),
    });
    expect(state.phase).toBe('conducting');
    expect(state.bodyEvent).toBe('attention_conduction');
    expect(state.conductorOrder).toEqual([upper.id, lower.id]);
    expect(state.waitingSurfaceIds).toEqual([upper.id]);
    expect(state.rootDominantRole).toBe('conducting');
    expect(state.invariant.valid).toBe(true);
  });

  it('lets approval hold override ordinary work', () => {
    const work = tab('content-1', 'content', { seatIndex: 2 });
    const approval = tab('approval-1', 'approval', { seatIndex: 3 });
    const state = lifecycle([work, approval], {
      focusId: approval.id,
      metabolism: approvalMetabolism,
      rootSystem: roots({ dominantRole: 'holding', heldSeatIndexes: [3] }),
    });
    expect(state.phase).toBe('approval_hold');
    expect(state.posture).toBe('holding_decision');
    expect(state.approvalSurfaceId).toBe(approval.id);
    expect(state.activeSurfaceId).toBe(approval.id);
  });

  it('turns scarred focused work into repair instead of ordinary work', () => {
    const work = tab('content-1', 'content', { seatIndex: 2 });
    const state = lifecycle([work], {
      focusId: work.id,
      metabolism: errorMetabolism,
      outcome: scarOutcome,
      rootSystem: roots({ dominantRole: 'error', errorSeatIndexes: [2] }),
    });
    expect(state.phase).toBe('error_repair');
    expect(state.bodyEvent).toBe('pain_return');
    expect(state.surfaces[0]).toMatchObject({ id: work.id, bodyRole: 'correction' });
  });

  it('owns completion settle and reabsorption as body states', () => {
    const work = tab('content-1', 'content', { seatIndex: 2 });
    const settling = lifecycle([work], {
      focusId: work.id,
      completion: completion({ state: 'settling', outcome: 'verified', targetId: work.id, targetKind: 'content' }),
    });
    expect(settling.phase).toBe('completion_settle');
    expect(settling.completionTargetId).toBe(work.id);
    expect(settling.surfaces[0]).toMatchObject({ bodyRole: 'completion' });

    const reabsorbingTab = { ...work, lifecycle: 'retracting' as const };
    const reabsorbing = lifecycle([reabsorbingTab], {
      focusId: work.id,
      completion: completion({ state: 'reabsorbing', outcome: 'verified', targetId: work.id, targetKind: 'content' }),
      rootSystem: roots({ dominantRole: 'reabsorbing', reabsorbingSeatIndexes: [2] }),
    });
    expect(reabsorbing.phase).toBe('reabsorbing');
    expect(reabsorbing.bodyEvent).toBe('memory_reabsorption');
    expect(reabsorbing.reabsorbingSurfaceIds).toContain(work.id);
  });

  it('flags stale intake when it overlaps active work', () => {
    const input = tab('input-1', 'input');
    const work = tab('content-1', 'content', { seatIndex: 2 });
    const state = lifecycle([input, work], { focusId: work.id });
    expect(state.phase).toBe('working');
    expect(state.staleSurfaceIds).toEqual([input.id]);
    expect(state.invariant.valid).toBe(false);
    expect(state.invariant.corruptionSignature).toContain('intake-overlaps-work');
  });

  it('flags duplicate workspace filepaths so replacement bugs are visible', () => {
    const older = tab('older', 'content', { seatIndex: 2, bornAt: 1, filepath: 'same.ts' });
    const newer = tab('newer', 'content', { seatIndex: 3, bornAt: 2, filepath: 'same.ts' });
    const state = lifecycle([older, newer], { focusId: newer.id });
    expect(state.phase).toBe('conducting');
    expect(state.staleSurfaceIds).toEqual([older.id]);
    expect(state.surfaces.find((surface) => surface.id === older.id)?.staleReason).toBe(
      'duplicate-workspace-filepath:same.ts',
    );
  });
});
