import { afterEach, describe, expect, it } from 'vitest';
import {
  getEmergencyStopPresentation,
  setEmergencyStopPresentation,
  subscribeEmergencyStopPresentation,
} from './emergencyStopPresentation';

describe('emergency stop presentation observation', () => {
  afterEach(() => {
    setEmergencyStopPresentation('unknown');
  });

  it('starts unknown and never treats unknown as engaged', () => {
    expect(getEmergencyStopPresentation()).toBe('unknown');
    expect(getEmergencyStopPresentation() === 'engaged').toBe(false);
  });

  it('publishes clear and engaged transitions to subscribers', () => {
    const seen: string[] = [];
    const unsubscribe = subscribeEmergencyStopPresentation(() => {
      seen.push(getEmergencyStopPresentation());
    });

    setEmergencyStopPresentation('clear');
    setEmergencyStopPresentation('engaged');
    unsubscribe();
    setEmergencyStopPresentation('unknown');

    expect(seen).toEqual(['clear', 'engaged']);
  });
});

