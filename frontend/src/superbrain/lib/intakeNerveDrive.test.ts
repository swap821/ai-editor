import { describe, it, expect } from 'vitest';
import { intakeNerveDrive } from './intakeNerveDrive';
import type { OrganismLifecyclePhase } from './organismLifecycle';

describe('intakeNerveDrive', () => {
  it('blazes at intake — the peak of receiving the operator', () => {
    expect(intakeNerveDrive('intake').drive).toBe(1.0);
    expect(intakeNerveDrive('intake').flow).toBe(1.0);
  });

  it('only the receiving phases carry bead flow', () => {
    const flowing: OrganismLifecyclePhase[] = ['attentive', 'intake'];
    const phases: OrganismLifecyclePhase[] = [
      'booting', 'arrival', 'rest', 'attentive', 'intake', 'materializing',
      'working', 'conducting', 'approval_hold', 'error_repair', 'completion_settle', 'reabsorbing',
    ];
    for (const p of phases) {
      const hasFlow = intakeNerveDrive(p).flow > 0;
      expect(hasFlow).toBe(flowing.includes(p));
    }
  });

  it('recedes while a work surface is up (mirrors the tail retract)', () => {
    // working/conducting must be quieter than rest, and quieter than intake
    expect(intakeNerveDrive('working').drive).toBeLessThan(intakeNerveDrive('rest').drive);
    expect(intakeNerveDrive('conducting').drive).toBeLessThan(intakeNerveDrive('working').drive);
    expect(intakeNerveDrive('working').drive).toBeLessThan(intakeNerveDrive('intake').drive);
  });

  it('is present but calm at rest, and dark before the being exists', () => {
    expect(intakeNerveDrive('rest').drive).toBeGreaterThan(0.2);
    expect(intakeNerveDrive('rest').drive).toBeLessThan(0.6);
    expect(intakeNerveDrive('booting').drive).toBe(0);
    expect(intakeNerveDrive('arrival').drive).toBe(0);
  });

  it('every drive/flow stays within [0,1]', () => {
    const phases: OrganismLifecyclePhase[] = [
      'booting', 'arrival', 'rest', 'attentive', 'intake', 'materializing',
      'working', 'conducting', 'approval_hold', 'error_repair', 'completion_settle', 'reabsorbing',
    ];
    for (const p of phases) {
      const d = intakeNerveDrive(p);
      expect(d.drive).toBeGreaterThanOrEqual(0);
      expect(d.drive).toBeLessThanOrEqual(1);
      expect(d.flow).toBeGreaterThanOrEqual(0);
      expect(d.flow).toBeLessThanOrEqual(1);
    }
  });
});
