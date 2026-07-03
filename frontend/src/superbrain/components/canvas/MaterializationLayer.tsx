import { useEffect } from 'react';
import { getLastEmittedCode, subscribePendingApproval, type PendingApproval } from '@/lib/aiosAdapter';
import { deriveAnatomicalConductor } from '@/lib/anatomicalConductor';
import { subscribeCognition } from '@/lib/cognitionBus';
import {
  getCompletionReflexSnapshot,
  ingestCompletionReflexEvent,
  markCompletionReflexReabsorbing,
  useCompletionReflex,
} from '@/lib/completionReflex';
import {
  getApprovalSurfacePlacement,
  getContentSurfacePlacement,
  getInputSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from '@/lib/materializedSurfaceAnchors';
import { deriveMaterializedSurfacePose } from '@/lib/materializedSurfacePose';
import { getOutcomeImprintSnapshot, useOutcomeImprint } from '@/lib/outcomeImprint';
import { deriveAnatomicalRootSystem } from '@/lib/anatomicalRootSystem';
import { deriveOrganMaterialState } from '@/lib/organMaterialState';
import { deriveOrganismLifecycle } from '@/lib/organismLifecycle';
import { deriveBodyPosture } from '@/lib/bodyPosture';
import { setOrganismPhase } from '@/lib/organismPhaseBus';
import { deriveSpinalRootActuator } from '@/lib/spinalRootActuator';
import { deriveSurfaceShapeGrammar, SURFACE_SHAPE_DIMENSIONS } from '@/lib/surfaceShapeGrammar';
import {
  beginRetractingMaterializedTab,
  focusMaterializedTab,
  focusNextMaterializedTab,
  focusPreviousMaterializedTab,
  getFocusedMaterializedTab,
  getMaterializedTabByKind,
  getOccupiedVertebraSeats,
  getSeatForPendingApproval,
  getTabStoreSnapshot,
  clearMaterializedTab,
  isWorkMaterializationClaimed,
  showApprovalSurface,
  showContentSurface,
  upsertInputSurface,
  useTabStore,
  type MaterializedApprovalSurface,
  type MaterializedTabContent,
} from '@/lib/tabStore';
import { deriveLivingOrchestration } from '@/lib/livingOrchestrator';
import { setConversationPhase } from '@/lib/conversationPhaseBus';
import { deriveDemoStatePlan, type DemoStateName } from '@/lib/demoStates';
import { getTurnMetabolismSnapshot, useTurnMetabolism } from '@/lib/turnMetabolism';
import AnatomicalConductorOverlay from './AnatomicalConductorOverlay';
import AttentionConductionPulse from './AttentionConductionPulse';
import CompletionMemoryBead from './CompletionMemoryBead';
import MaterializedTab from './MaterializedTab';
import ReabsorptionParticles from './ReabsorptionParticles';
import { readBeingMode } from '@/lib/beingMode';

// Point-field being: the per-tab umbilical (MaterializedTab) + the conversation/
// completion postures cover conduction; the mesh-era scene overlays render at
// mesh-spine coords (a misplaced ring + sprawling lines in points) — gate off.
const POINTS = readBeingMode() === 'points';

const DEV_STUB_CONTENT: MaterializedTabContent = {
  code: "export function hello(name = 'GAGOS') {\n  return `Hello, ${name}`;\n}\n",
  language: 'javascript',
  filepath: 'hello.js',
};

function normalizeContent(content: MaterializedTabContent | null): MaterializedTabContent | null {
  if (!content) return null;
  const code = String(content.code ?? '');
  if (!code.trim()) return null;
  return {
    code,
    language: String(content.language ?? 'text'),
    filepath: String(content.filepath ?? 'materialized.txt'),
  };
}

function normalizeApproval(pending: PendingApproval | null): MaterializedApprovalSurface | null {
  if (!pending) return null;
  return {
    token: String(pending.token ?? ''),
    summary: String(pending.summary ?? 'Approval required'),
    explanation: String(pending.explanation ?? ''),
    diff: String(pending.diff ?? ''),
    command: String(pending.command ?? ''),
    kindLabel: String(pending.kind ?? 'other'),
    filepath: String(pending.filepath ?? ''),
    content: String(pending.content ?? ''),
  };
}

function reabsorbInputSurface(): void {
  const input = getMaterializedTabByKind('input');
  if (input?.kind === 'input' && input.lifecycle !== 'retracting') {
    beginRetractingMaterializedTab(input.id);
  }
}

export default function MaterializationLayer({ reducedMotion }: { reducedMotion: boolean }) {
  const { tabs, focusId, attention } = useTabStore();
  const metabolism = useTurnMetabolism();
  const outcome = useOutcomeImprint();
  const completion = useCompletionReflex();

  useEffect(
    () =>
      subscribeCognition((event) => {
        ingestCompletionReflexEvent(event, getFocusedMaterializedTab());
      }),
    [],
  );

  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type !== 'knowledge-acquired' || event.label !== 'CODE EMITTED') return;
        // GagosChrome owns work materialization during its turn; skip so we don't
        // spawn a duplicate of the tab it will create from the same code emission.
        if (isWorkMaterializationClaimed()) return;
        const content = normalizeContent(getLastEmittedCode());
        if (!content) return;
        const approvalSeat = getSeatForPendingApproval(content.filepath);
        const seatIndex = approvalSeat ?? selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
        reabsorbInputSurface();
        showContentSurface(content, getContentSurfacePlacement(seatIndex));
        const approval = getMaterializedTabByKind('approval');
        if (approval && (approvalSeat === null || approval.seatIndex === approvalSeat)) {
          beginRetractingMaterializedTab(approval.id);
        }
      }),
    [],
  );

  useEffect(
    () =>
      subscribePendingApproval((pending) => {
        const approval = normalizeApproval(pending);
        if (approval) {
          const current = getMaterializedTabByKind('approval');
          const seatIndex = current?.seatIndex ?? selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
          reabsorbInputSurface();
          showApprovalSurface(approval, getApprovalSurfacePlacement(seatIndex));
          return;
        }
        const current = getMaterializedTabByKind('approval');
        if (current?.kind === 'approval' && current.approval?.token !== 'dev-approval') {
          beginRetractingMaterializedTab(current.id);
        }
      }),
    [],
  );

  useEffect(() => {
    if (!completion.reabsorbReady || !completion.targetId) return;

    const target = getTabStoreSnapshot().tabs.find((tab) => tab.id === completion.targetId);
    if (!target || target.lifecycle === 'retracting') {
      markCompletionReflexReabsorbing(completion.targetId);
      return;
    }
    if (target.kind === 'input' || target.lifecycle !== 'live') return;

    markCompletionReflexReabsorbing(target.id);
    beginRetractingMaterializedTab(target.id);
  }, [completion.intensity, completion.reabsorbReady, completion.targetId]);

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return undefined;
    const host = window as typeof window & {
      __materializeTab?: (content?: Partial<MaterializedTabContent>) => unknown;
      __materializeInput?: (text?: string) => unknown;
      __materializeApproval?: (partial?: Partial<MaterializedApprovalSurface>) => unknown;
      __demo?: (name: DemoStateName) => unknown;
      __focusMaterializedTab?: (id: string) => void;
      __conductNextMaterializedTab?: () => unknown;
      __conductPreviousMaterializedTab?: () => unknown;
      __reabsorbMaterializedTab?: (id?: string) => void;
      __getMaterializedTabs?: typeof getTabStoreSnapshot;
      __getLivingOrchestration?: () => ReturnType<typeof deriveLivingOrchestration>;
      __getTurnMetabolism?: typeof getTurnMetabolismSnapshot;
      __getOutcomeImprint?: typeof getOutcomeImprintSnapshot;
      __getCompletionReflex?: typeof getCompletionReflexSnapshot;
      __getAnatomicalConductor?: () => ReturnType<typeof deriveAnatomicalConductor>;
      __getAnatomicalRootSystem?: () => ReturnType<typeof deriveAnatomicalRootSystem>;
      __getOrganismLifecycle?: () => ReturnType<typeof deriveOrganismLifecycle>;
      __getSpinalRootActuators?: () => unknown;
      __getOrganMaterialStates?: () => unknown;
      __getSurfaceShapeGrammars?: () => unknown;
    };
    host.__materializeTab = (content = {}) => {
      const next = normalizeContent({
        ...DEV_STUB_CONTENT,
        ...content,
      });
      if (!next) return null;
      const seatIndex = selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
      reabsorbInputSurface();
      return showContentSurface(next, getContentSurfacePlacement(seatIndex));
    };
    host.__materializeInput = (text = 'build a living input surface') => {
      return upsertInputSurface(text, getInputSurfacePlacement());
    };
    host.__materializeApproval = (partial = {}) => {
      const seatIndex = selectNextAvailableVertebraSeat(getOccupiedVertebraSeats());
      reabsorbInputSurface();
      return showApprovalSurface(
        {
          token: 'dev-approval',
          summary: 'Approval required to materialize demo.py',
          explanation: 'Dev-only approval surface for embodied review.',
          diff: '+export const demo = true;\n',
          command: '',
          kindLabel: 'create',
          filepath: 'demo.py',
          content: 'export const demo = true;\n',
          ...partial,
        },
        getApprovalSurfacePlacement(seatIndex),
      );
    };
    host.__getMaterializedTabs = getTabStoreSnapshot;
    host.__focusMaterializedTab = focusMaterializedTab;
    host.__conductNextMaterializedTab = focusNextMaterializedTab;
    host.__conductPreviousMaterializedTab = focusPreviousMaterializedTab;
    host.__reabsorbMaterializedTab = beginRetractingMaterializedTab;
    // Proof harness: drive the organism into a canonical poster state, persistently
    // (window.__demo('orchestrate3') etc.). Composes the existing primitives per the
    // pure plan — distinct filepaths so multi-surface appends; conversation phase as
    // the override driver; surfaces drive the structural phases emergently. See
    // lib/demoStates.ts + .aios/state/PROOF_SWEEP.md.
    host.__demo = (name: DemoStateName) => {
      const plan = deriveDemoStatePlan(name);
      clearMaterializedTab(); // clean slate (clears all surfaces)
      reabsorbInputSurface();
      for (const s of plan.surfaces) {
        const placement = getContentSurfacePlacement(s.seatIndex);
        showContentSurface({ code: s.code, language: s.language, filepath: s.filepath }, placement);
      }
      setConversationPhase(plan.conversation ?? 'idle');
      if (plan.reabsorbFocused) {
        const focusId = getTabStoreSnapshot().focusId;
        if (focusId) beginRetractingMaterializedTab(focusId);
      }
      const o = deriveLivingOrchestration(getTabStoreSnapshot());
      return { name, surfaces: plan.surfaces.length, workspaceCount: o.workspaceCount, conversation: plan.conversation };
    };
    host.__getLivingOrchestration = () => deriveLivingOrchestration(getTabStoreSnapshot());
    host.__getTurnMetabolism = getTurnMetabolismSnapshot;
    host.__getOutcomeImprint = getOutcomeImprintSnapshot;
    host.__getCompletionReflex = getCompletionReflexSnapshot;
    host.__getAnatomicalConductor = () => {
      const snapshot = getTabStoreSnapshot();
      const orchestration = deriveLivingOrchestration(snapshot);
      return deriveAnatomicalConductor({ tabs: snapshot.tabs, orchestration });
    };
    host.__getAnatomicalRootSystem = () => {
      const snapshot = getTabStoreSnapshot();
      const orchestration = deriveLivingOrchestration(snapshot);
      return deriveAnatomicalRootSystem({
        surfaces: orchestration.surfaces,
        metabolism: getTurnMetabolismSnapshot(),
        outcome: getOutcomeImprintSnapshot(),
      });
    };
    host.__getOrganismLifecycle = () => {
      const snapshot = getTabStoreSnapshot();
      const orchestration = deriveLivingOrchestration(snapshot);
      const currentMetabolism = getTurnMetabolismSnapshot();
      const currentOutcome = getOutcomeImprintSnapshot();
      const currentCompletion = getCompletionReflexSnapshot();
      const currentRootSystem = deriveAnatomicalRootSystem({
        surfaces: orchestration.surfaces,
        metabolism: currentMetabolism,
        outcome: currentOutcome,
      });
      return deriveOrganismLifecycle({
        orchestration,
        metabolism: currentMetabolism,
        outcome: currentOutcome,
        completion: currentCompletion,
        rootSystem: currentRootSystem,
      });
    };
    host.__getSpinalRootActuators = () => {
      const snapshot = getTabStoreSnapshot();
      const orchestration = deriveLivingOrchestration(snapshot);
      const currentMetabolism = getTurnMetabolismSnapshot();
      const currentOutcome = getOutcomeImprintSnapshot();
      return orchestration.surfaces.map(({ tab, focused, waitingIndex, role }) => ({
        id: tab.id,
        kind: tab.kind,
        lifecycle: tab.lifecycle,
        surfaceRole: role,
        ...deriveSpinalRootActuator({
          kind: tab.kind,
          lifecycle: tab.lifecycle,
          focused,
          waitingIndex,
          metabolism: currentMetabolism,
          outcome: currentOutcome,
        }),
      }));
    };
    host.__getOrganMaterialStates = () => {
      const snapshot = getTabStoreSnapshot();
      const orchestration = deriveLivingOrchestration(snapshot);
      const currentMetabolism = getTurnMetabolismSnapshot();
      const currentOutcome = getOutcomeImprintSnapshot();
      return orchestration.surfaces.map(({ tab, focused, waitingIndex, role }) => {
        const isFocused = tab.kind === 'input' || focused;
        const actuator = deriveSpinalRootActuator({
          kind: tab.kind,
          lifecycle: tab.lifecycle,
          focused: isFocused,
          waitingIndex,
          metabolism: currentMetabolism,
          outcome: currentOutcome,
        });
        return {
          id: tab.id,
          kind: tab.kind,
          lifecycle: tab.lifecycle,
          surfaceRole: role,
          ...deriveOrganMaterialState({
            kind: tab.kind,
            lifecycle: tab.lifecycle,
            focused: isFocused,
            waitingIndex,
            metabolism: currentMetabolism,
            outcome: currentOutcome,
            actuator,
          }),
        };
      });
    };
    host.__getSurfaceShapeGrammars = () => {
      const snapshot = getTabStoreSnapshot();
      const orchestration = deriveLivingOrchestration(snapshot);
      const currentMetabolism = getTurnMetabolismSnapshot();
      const currentOutcome = getOutcomeImprintSnapshot();
      return orchestration.surfaces.map(({ tab, focused, waitingIndex, role }) => {
        const isFocused = tab.kind === 'input' || focused;
        const pose = deriveMaterializedSurfacePose({
          kind: tab.kind,
          focused: isFocused,
          targetLocal: tab.targetLocal,
          waitingIndex,
        });
        const actuator = deriveSpinalRootActuator({
          kind: tab.kind,
          lifecycle: tab.lifecycle,
          focused: isFocused,
          waitingIndex,
          metabolism: currentMetabolism,
          outcome: currentOutcome,
        });
        const material = deriveOrganMaterialState({
          kind: tab.kind,
          lifecycle: tab.lifecycle,
          focused: isFocused,
          waitingIndex,
          metabolism: currentMetabolism,
          outcome: currentOutcome,
          actuator,
        });
        return {
          id: tab.id,
          kind: tab.kind,
          lifecycle: tab.lifecycle,
          surfaceRole: role,
          ...deriveSurfaceShapeGrammar({
            kind: tab.kind,
            lifecycle: tab.lifecycle,
            focused: isFocused,
            waitingIndex,
            role: material.role,
            originLocal: tab.originLocal,
            targetLocal: pose.targetLocal,
            dimensions: SURFACE_SHAPE_DIMENSIONS[tab.kind],
            rootGripCount: tab.kind === 'input' ? 0 : 4,
            actuator,
          }),
        };
      });
    };
    return () => {
      delete host.__materializeTab;
      delete host.__materializeInput;
      delete host.__materializeApproval;
      delete host.__demo;
      delete host.__focusMaterializedTab;
      delete host.__conductNextMaterializedTab;
      delete host.__conductPreviousMaterializedTab;
      delete host.__reabsorbMaterializedTab;
      delete host.__getMaterializedTabs;
      delete host.__getLivingOrchestration;
      delete host.__getTurnMetabolism;
      delete host.__getOutcomeImprint;
      delete host.__getCompletionReflex;
      delete host.__getAnatomicalConductor;
      delete host.__getAnatomicalRootSystem;
      delete host.__getOrganismLifecycle;
      delete host.__getSpinalRootActuators;
      delete host.__getOrganMaterialStates;
      delete host.__getSurfaceShapeGrammars;
    };
  }, []);

  const orchestration = deriveLivingOrchestration({ tabs, focusId, attention });
  const anatomy = deriveAnatomicalConductor({ tabs, orchestration });
  const rootSystem = deriveAnatomicalRootSystem({ surfaces: orchestration.surfaces, metabolism, outcome });
  const organism = deriveOrganismLifecycle({ orchestration, metabolism, outcome, completion, rootSystem });
  const completionVisible = organism.completionState !== 'idle' && organism.completionState !== 'held';

  // Publish the live phase to the scene-root frame loop (drives the spectral-v1
  // body posture color/flow). Hook stays above the early return so it runs every
  // render, including at rest when this layer renders nothing.
  useEffect(() => {
    setOrganismPhase(organism.phase);
  }, [organism.phase]);

  const bodyPosture = deriveBodyPosture({ phase: organism.phase });

  if (orchestration.surfaces.length === 0 && !completionVisible) return null;

  return (
    <>
      {!POINTS && (
        <>
          <AnatomicalConductorOverlay anatomy={anatomy} rootSystem={rootSystem} reducedMotion={reducedMotion} bodyPosture={bodyPosture} />
          <AttentionConductionPulse tabs={tabs} attention={orchestration.attention} reducedMotion={reducedMotion} />
          <CompletionMemoryBead reflex={completion} reducedMotion={reducedMotion} />
        </>
      )}
      {/* The input surface is brainstem-anatomy and is rendered by BrainstemIntake
          (the brainstem owns intake). The vertebra-seated work/approval/content
          surfaces are rendered here. Excluding kind:'input' collapses the former
          duplicate input render (one renderer per surface). */}
      {orchestration.surfaces
        .filter(({ tab }) => tab.kind !== 'input')
        .map(({ tab, focused, waitingIndex }) => (
          <MaterializedTab
            key={tab.id}
            tab={tab}
            reducedMotion={reducedMotion}
            focused={focused}
            waitingIndex={waitingIndex}
            workspaceCount={orchestration.workspaceCount}
            posture={bodyPosture}
            metabolism={metabolism}
            outcome={outcome}
          />
        ))}
      {/* CorticalNerve (cortex -> work surface) REMOVED (operator call 2026-06-23):
          the nerve reaching from the brain cortex to the panel read as weird. The
          tab keeps its vertebra umbilical; only this extra cortical reach is gone. */}
      {/* Phase 7: a retracting work slab dissolves into motes that stream up the
          spine back into the brain (points being). */}
      {POINTS &&
        orchestration.surfaces
          .filter(({ tab }) => tab.kind !== 'input' && tab.lifecycle === 'retracting')
          .map(({ tab }) => (
            <ReabsorptionParticles
              key={`reabsorb-${tab.id}`}
              origin={tab.originLocal}
              startedAt={tab.phaseStartedAt}
              durationMs={1700}
              color={completion.tint}
              reducedMotion={reducedMotion}
            />
          ))}
    </>
  );
}
