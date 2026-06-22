// demoStates — the pure descriptor for the GAGOS state proof harness.
//
// Each canonical poster state maps to the setup that DRIVES the organism into it,
// via TWO levers that the live render already obeys:
//   • SURFACES — showContentSurface() with DISTINCT filepaths (it dedups by
//     filepath, so distinct paths are what make multi-surface orchestration
//     append). Surfaces drive the STRUCTURAL phases emergently: 1 fresh surface →
//     'materializing', 3 → 'conducting', a retracting one → 'reabsorbing'.
//   • CONVERSATION phase — setConversationPhase(); BrainPointField reads
//     conversationToOrganismPhase(conv) ?? organismPhase, so the conversation bus
//     OVERRIDES the emergent phase for the reply/outcome body states (thinking →
//     attentive, streaming → working, complete → completion_settle, error →
//     error_repair). This is why we drive conversation, NOT setOrganismPhase
//     (which MaterializationLayer re-derives + overwrites every render).
//
// Pure (no DOM / side effects): the window.__demo() dev hook reads a plan and
// applies it by composing those EXISTING primitives. Invents no product behavior —
// the states already exist; this only makes them reliably DRIVABLE for the
// 10-state proof sweep + regression coverage.

import type { ConversationPhase } from './conversationPhaseBus';

export type DemoStateName =
  | 'rest'
  | 'intake'
  | 'awakening'
  | 'materialize'
  | 'orchestrate3'
  | 'streaming'
  | 'error'
  | 'completion'
  | 'reabsorbing';

export const DEMO_STATE_NAMES: readonly DemoStateName[] = [
  'rest',
  'intake',
  'awakening',
  'materialize',
  'orchestrate3',
  'streaming',
  'error',
  'completion',
  'reabsorbing',
];

export interface DemoSurfaceSpec {
  /** distinct per surface — showContentSurface dedups by filepath, so a unique
   *  filepath is what makes multi-surface orchestration actually append. */
  filepath: string;
  language: string;
  code: string;
  /** vertebra seat to dock on. */
  seatIndex: number;
}

export interface DemoStatePlan {
  /** content surfaces to seat (empty = bare body). Drives structural phases. */
  surfaces: DemoSurfaceSpec[];
  /** conversation phase to drive (overrides the emergent body phase), or null. */
  conversation: ConversationPhase | null;
  /** reabsorb the focused surface (State 9 — energy returns up the spine). */
  reabsorbFocused: boolean;
}

/** A single demo work surface (fresh array each call — never share a reference). */
const oneSurface = (): DemoSurfaceSpec[] => [
  { filepath: 'work.ts', language: 'typescript', code: 'export const run = () => compute(input);\n', seatIndex: 0 },
];

export function deriveDemoStatePlan(name: DemoStateName): DemoStatePlan {
  switch (name) {
    case 'rest':
      return { surfaces: [], conversation: null, reabsorbFocused: false };
    case 'intake':
      return { surfaces: [], conversation: 'awakening', reabsorbFocused: false };
    case 'awakening':
      return { surfaces: [], conversation: 'thinking', reabsorbFocused: false };
    case 'materialize':
      return { surfaces: oneSurface(), conversation: null, reabsorbFocused: false };
    case 'orchestrate3':
      return {
        surfaces: [
          { filepath: 'research.md', language: 'markdown', code: '# research\n- finding a\n- finding b\n', seatIndex: 0 },
          { filepath: 'plan.ts', language: 'typescript', code: 'export const plan = [1, 2, 3];\n', seatIndex: 2 },
          { filepath: 'build.log', language: 'text', code: 'build ok\nlint ok\n', seatIndex: 4 },
        ],
        conversation: null,
        reabsorbFocused: false,
      };
    case 'streaming':
      return { surfaces: oneSurface(), conversation: 'streaming', reabsorbFocused: false };
    case 'error':
      return { surfaces: oneSurface(), conversation: 'error', reabsorbFocused: false };
    case 'completion':
      return { surfaces: oneSurface(), conversation: 'complete', reabsorbFocused: false };
    case 'reabsorbing':
      return { surfaces: oneSurface(), conversation: null, reabsorbFocused: true };
    default: {
      const unreachable: never = name;
      throw new Error(`unknown demo state: ${String(unreachable)}`);
    }
  }
}
