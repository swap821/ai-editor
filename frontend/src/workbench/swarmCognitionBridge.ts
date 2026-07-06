/**
 * swarmCognitionBridge — the being finally FEELS its swarm.
 *
 * The swarmHUDStore already receives every ant-colony lifecycle frame from the
 * adapter (swarm_plan / caste_start / caste_end / cloud_route), but only the
 * 2D SwarmHUD read it — the 3D organism and the cognition terminal stayed
 * blind to the colony working inside it. This bridge subscribes to the store
 * and narrates STATE TRANSITIONS onto the cognition bus using the existing
 * `agent-dispatch` event type (source: 'swarm'), so the body, terminal, and
 * intake organs react through their current handlers — no new scene wiring,
 * no cognition-type additions, palette untouched.
 *
 * Product-safe by construction: a NEW workbench file that only imports from
 * the ported lab modules (imports are fine; edits are not).
 */
import { publishCognition } from '../superbrain/lib/cognitionBus';
import { subscribeSwarmHUD, type SwarmHUDState } from '../superbrain/lib/swarmHUDStore';

function narrate(prev: SwarmHUDState, next: SwarmHUDState): void {
  // Plan arrival: a new decomposition replaces the old one (startSwarmPlan
  // resets castes/legs, so a fresh non-empty plan array is the signal).
  if (next.plan.length > 0 && next.plan !== prev.plan) {
    publishCognition({
      type: 'agent-dispatch',
      label: 'SWARM DECOMPOSED',
      detail: `${next.plan.length} subtask(s): ${next.plan.map((p) => p.slice(0, 40)).join(' · ')}`.slice(0, 160),
      intensity: 0.7,
      source: 'swarm',
      data: { plan: next.plan },
    });
  }
  for (const caste of next.activeCastes) {
    if (!prev.activeCastes.includes(caste)) {
      publishCognition({
        type: 'agent-dispatch',
        label: `CASTE ${caste.toUpperCase()}`,
        detail: 'an ephemeral caste takes up its one job',
        intensity: 0.5,
        source: 'swarm',
        data: { caste, phase: 'start' },
      });
    }
  }
  for (const caste of prev.activeCastes) {
    if (!next.activeCastes.includes(caste)) {
      publishCognition({
        type: 'agent-dispatch',
        label: `CASTE ${caste.toUpperCase()} DONE`,
        detail: `${next.completedLegs} leg(s) complete — the worker dissolves`,
        intensity: 0.45,
        source: 'swarm',
        data: { caste, phase: 'end', completedLegs: next.completedLegs },
      });
    }
  }
  for (const index of next.cloudIndices) {
    if (!prev.cloudIndices.includes(index)) {
      publishCognition({
        type: 'agent-dispatch',
        label: 'SWARM CLOUD BURST',
        detail: `subtask ${index + 1} routed to the cloud factory`,
        intensity: 0.6,
        source: 'swarm',
        data: { subtaskIndex: index },
      });
    }
  }
}

function isResetState(state: SwarmHUDState): boolean {
  return (
    !state.active &&
    state.plan.length === 0 &&
    state.activeCastes.length === 0 &&
    state.completedLegs === 0 &&
    state.cloudIndices.length === 0
  );
}

/** Mount once (GagosChrome effect). Returns the unsubscribe for cleanup. */
export function initSwarmCognitionBridge(): () => void {
  let prev: SwarmHUDState | null = null;
  return subscribeSwarmHUD((next) => {
    // subscribeSwarmHUD replays the current state immediately on subscribe;
    // treat that snapshot as the baseline, never as a transition to narrate.
    // A reset (sendDirective clears the store at the start of every turn) is
    // ALSO not a transition: castes an aborted swarm left behind must not be
    // falsely narrated as completing when the next unrelated turn begins.
    if (prev !== null && !isResetState(next)) narrate(prev, next);
    prev = next;
  });
}
