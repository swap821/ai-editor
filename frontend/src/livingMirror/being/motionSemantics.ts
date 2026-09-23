import type { BeingMotion } from './semanticKernel';

export interface BeingMotionSemantics {
  id: `motion.${BeingMotion}`;
  meaning: string;
  startCondition: string;
  endCondition: string;
  reducedMotion: string;
}

/**
 * Product-owned motion contract. Renderer implementations may choose different
 * amplitudes at each quality tier, but may not change what a motion claims.
 */
export const BEING_MOTION_SEMANTICS: Record<BeingMotion, BeingMotionSemantics> = {
  calm: {
    id: 'motion.calm',
    meaning: 'The organism is resting without an active task.',
    startCondition: 'No attention, action, approval, verification, or stop posture is measured.',
    endCondition: 'A measured human, workspace, approval, or system-state transition arrives.',
    reducedMotion: 'Keep a stable luminance and silhouette; omit breathing travel.',
  },
  attention: {
    id: 'motion.attention',
    meaning: 'The organism is oriented toward human input, planning, or learning.',
    startCondition: 'Input, understanding, planning, approval, or learning is measured.',
    endCondition: 'The attention source is resolved, replaced by action, or becomes stale.',
    reducedMotion: 'Use a static focus accent and an ARIA/live-text explanation.',
  },
  materialize: {
    id: 'motion.materialize',
    meaning: 'A meaningful workspace is growing from the being.',
    startCondition: 'The body or a content tab reports arrival, reaching, unfurling, or materializing.',
    endCondition: 'The workspace is live and readable, or the lifecycle is retracted/stale.',
    reducedMotion: 'Cross-fade the workspace and transfer focus without travel.',
  },
  conduct: {
    id: 'motion.conduct',
    meaning: 'Measured work is conducting through the being and workspace.',
    startCondition: 'Streaming work or an active/reflex worker is observed.',
    endCondition: 'Work returns, verification begins, stop engages, or state becomes stale.',
    reducedMotion: 'Show a stable active marker and progress text; omit directional travel.',
  },
  verify: {
    id: 'motion.verify',
    meaning: 'The result is being checked before it becomes solid truth.',
    startCondition: 'Verification is pending or checking is measured.',
    endCondition: 'A pass, fail, stop, or stale boundary is measured.',
    reducedMotion: 'Use a static checking indicator and announce the resulting verdict.',
  },
  refuse: {
    id: 'motion.refuse',
    meaning: 'A controlled boundary stopped an action that exceeded permission.',
    startCondition: 'A refusal or injection block is measured.',
    endCondition: 'The refusal receipt is presented and a safe next action is available.',
    reducedMotion: 'Use a calm boundary state and focus the explanation/next-action control.',
  },
  reabsorb: {
    id: 'motion.reabsorb',
    meaning: 'Completed, failed, or restored work is returning to the organism without losing evidence.',
    startCondition: 'Rollback, verification failure, failed work, or a retracting/reabsorbing lifecycle is measured.',
    endCondition: 'The surface is inactive and its receipt remains available, or recovery needs a human next step.',
    reducedMotion: 'Fade the surface and preserve the receipt; do not animate travel.',
  },
  stop: {
    id: 'motion.stop',
    meaning: 'Emergency stop overrides action presentation.',
    startCondition: 'Emergency stop is engaged.',
    endCondition: 'A fresh, explicit recovery state replaces the stop posture.',
    reducedMotion: 'Freeze action-bearing structures and keep stop status visible.',
  },
};

export function motionSemanticsFor(motion: BeingMotion): BeingMotionSemantics {
  return BEING_MOTION_SEMANTICS[motion];
}
