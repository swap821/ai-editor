import { describe, expect, it } from 'vitest';
import {
  createOutcomeImprintSignals,
  deriveOutcomeImprintSnapshot,
  reduceOutcomeImprintEvent,
} from './outcomeImprint';

const NOW = 20_000;

describe('outcomeImprint', () => {
  it('rests when no verified outcome has stamped the body', () => {
    const imprint = deriveOutcomeImprintSnapshot(createOutcomeImprintSignals(), NOW);

    expect(imprint).toMatchObject({
      kind: 'none',
      intensity: 0,
      ringOpacity: 0,
      scarOpacity: 0,
      rootGlow: 0,
    });
  });

  it('turns verification green into a short-lived verified afterglow', () => {
    const signals = reduceOutcomeImprintEvent(
      createOutcomeImprintSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION GREEN', detail: 'pytest passed' },
      NOW,
    );

    const imprint = deriveOutcomeImprintSnapshot(signals, NOW + 500);

    expect(imprint.kind).toBe('verified');
    expect(imprint.tint).toBe('#8dffd1');
    expect(imprint.rootGlow).toBeGreaterThan(imprint.surfaceGlow);
    expect(imprint.scarOpacity).toBeLessThan(imprint.ringOpacity);
    expect(imprint.label).toBe('VERIFICATION GREEN');
  });

  it('turns verification red and rejected approvals into scars', () => {
    const red = reduceOutcomeImprintEvent(
      createOutcomeImprintSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION RED' },
      NOW,
    );
    const rejected = reduceOutcomeImprintEvent(
      createOutcomeImprintSignals(),
      { type: 'approval-resolved', label: 'rejected' },
      NOW,
    );

    const redImprint = deriveOutcomeImprintSnapshot(red, NOW + 300);
    const rejectedImprint = deriveOutcomeImprintSnapshot(rejected, NOW + 300);

    expect(redImprint.kind).toBe('scar');
    expect(rejectedImprint.kind).toBe('scar');
    expect(redImprint.scarOpacity).toBeGreaterThan(redImprint.ringOpacity);
    expect(redImprint.tint).toBe('#ff5f7a');
  });

  it('stamps an accepted glow for approved human decisions', () => {
    const signals = reduceOutcomeImprintEvent(
      createOutcomeImprintSignals(),
      { type: 'approval-resolved', label: 'approved' },
      NOW,
    );

    const imprint = deriveOutcomeImprintSnapshot(signals, NOW + 250);

    expect(imprint.kind).toBe('accepted');
    expect(imprint.ringOpacity).toBeGreaterThan(0);
    expect(imprint.scarOpacity).toBeLessThan(imprint.ringOpacity);
  });

  it('lets the newest outcome replace the previous body memory', () => {
    let signals = createOutcomeImprintSignals();
    signals = reduceOutcomeImprintEvent(signals, { type: 'knowledge-acquired', label: 'VERIFICATION GREEN' }, NOW);
    signals = reduceOutcomeImprintEvent(signals, { type: 'knowledge-acquired', label: 'VERIFICATION RED' }, NOW + 700);

    const imprint = deriveOutcomeImprintSnapshot(signals, NOW + 900);

    expect(imprint.kind).toBe('scar');
    expect(imprint.changedAt).toBe(NOW + 700);
  });

  it('decays stale outcomes back to no imprint', () => {
    const signals = reduceOutcomeImprintEvent(
      createOutcomeImprintSignals(),
      { type: 'knowledge-acquired', label: 'VERIFICATION GREEN' },
      NOW,
    );

    expect(deriveOutcomeImprintSnapshot(signals, NOW + 6201).kind).toBe('none');
  });
});
