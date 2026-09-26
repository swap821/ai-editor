import { describe, expect, it } from 'vitest';
import type { BeingPresentation } from './semanticKernel';
import { applyEmergencyStopPresentation } from './emergencyStopOverlay';

const active: BeingPresentation = {
  phase: 'acting',
  taskState: 'working',
  coherence: 'fresh',
  motion: 'conduct',
  attention: 'workspace',
  signals: ['worker-active'],
  workers: [{ workerId: 'worker-0', state: 'active', cursor: 0 }],
};

describe('emergency stop presentation overlay', () => {
  it('freezes the body posture when the measured latch is engaged', () => {
    expect(applyEmergencyStopPresentation(active, 'engaged')).toMatchObject({
      phase: 'stopped',
      taskState: 'stopped',
      coherence: 'stopped',
      motion: 'stop',
      attention: 'none',
      signals: ['emergency-stop', 'worker-active'],
      workers: [{ workerId: 'worker-0', state: 'active', cursor: 0 }],
    });
  });

  it('does not treat unknown or clear observations as a stop', () => {
    expect(applyEmergencyStopPresentation(active, 'unknown')).toBe(active);
    expect(applyEmergencyStopPresentation(active, 'clear')).toBe(active);
  });
});

