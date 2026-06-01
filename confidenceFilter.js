// confidenceFilter.js
// Second, independent gating layer (orthogonal to the security zone).
// Any step below the confidence threshold escalates to human review,
// regardless of how safe its security zone is.

export const CONFIDENCE_THRESHOLD = 0.72;

/**
 * Partition planned steps into auto-approved vs. human-escalation.
 * @param {Array<{ step_id?: string, description?: string, confidence: number }>} steps
 * @param {number} [threshold]
 * @returns {{ approved: Array, escalate: Array }}
 */
export function filterSteps(steps, threshold = CONFIDENCE_THRESHOLD) {
  const approved = [];
  const escalate = [];
  for (const step of steps || []) {
    const c = typeof step.confidence === 'number' ? step.confidence : 0;
    if (c >= threshold) {
      approved.push(step);
    } else {
      escalate.push({
        step,
        reason: `Confidence ${c.toFixed(3)} below threshold ${threshold}`,
        action: 'REQUIRE_HUMAN_REVIEW',
      });
    }
  }
  return { approved, escalate };
}

/**
 * Convenience single-value gate.
 * @param {number} confidence
 * @param {number} [threshold]
 * @returns {{ passed: boolean, reason: string }}
 */
export function gate(confidence, threshold = CONFIDENCE_THRESHOLD) {
  const c = typeof confidence === 'number' ? confidence : 0;
  const passed = c >= threshold;
  return {
    passed,
    reason: passed
      ? `Confidence ${c.toFixed(3)} meets threshold ${threshold}`
      : `Confidence ${c.toFixed(3)} below threshold ${threshold} — human review required`,
  };
}
