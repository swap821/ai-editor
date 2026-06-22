/**
 * organismPhaseBus — a tiny module-level handoff of the live organism lifecycle
 * phase, from the React layer (MaterializationLayer, which derives the full
 * organism snapshot every render) to the R3F scene-root frame loop
 * (SuperbrainScene), which needs the phase every frame to drive the spectral-v1
 * posture color/flow.
 *
 * Why a module ref and not a prop/context: the scene root reads it inside
 * useFrame (not React render), and MaterializationLayer + SuperbrainScene live
 * in different parts of the tree. This mirrors how the SCENE_UNIFORMS leaves
 * already cross the same boundary. It is NOT app state — just the latest phase,
 * read-mostly, written on lifecycle change.
 */
import type { OrganismLifecyclePhase } from './organismLifecycle';

let currentPhase: OrganismLifecyclePhase = 'rest';

/** Publish the latest organism lifecycle phase (called by MaterializationLayer). */
export function setOrganismPhase(phase: OrganismLifecyclePhase): void {
  currentPhase = phase;
}

/** Read the latest organism lifecycle phase (called by the scene-root frame loop). */
export function getOrganismPhase(): OrganismLifecyclePhase {
  return currentPhase;
}
